#!/usr/bin/env python2.4

"""
    Preprocess a file.

    Command Line Usage:
        preprocess [<options>...] <infile>

    Options:
        -h, --help      Print this help and exit.
        -V, --version   Print the version info and exit.
        -v, --verbose   Give verbose output for errors.

        -o <outfile>    Write output to the given file instead of to stdout.
        -f, --force     Overwrite given output file. (Otherwise an IOError
                        will be raised if <outfile> already exists.
        -D <define>     Define a variable for preprocessing. <define>
                        can simply be a variable name (in which case it
                        will be true) or it can be of the form
                        <var>=<val>. An attempt will be made to convert
                        <val> to an integer so "-D FOO=0" will create a
                        false value.

        -k, --keep-lines    Emit empty lines for preprocessor statement
                        lines and skipped output lines. This allows line
                        numbers to stay constant.
        -s, --substitute    Substitute defines into emitted lines. By
                        default substitution is NOT done because it
                        currently will substitute into program strings.

    Module Usage:
        from preprocess import preprocess
        preprocess(infile, outfile=sys.stdout, defines={}, force=0)

    The <infile> can be marked up with special preprocessor statement lines
    of the form:
        <comment-prefix> <preprocessor-stmt> <comment-suffix>
    where the <comment-prefix/suffix> are the native comment delimiters for
    that file type. Examples:
        <!-- #if FOO -->
        ...
        <!-- #endif -->
    
        # #if defined('FAV_COLOR') and FAV_COLOR == "blue"
        ...
        # #elif FAV_COLOR == "red"
        ...
        # #else
        ...
        # #endif

    Preprocessor Syntax:
        - Valid statements:
            #define <var>[=<value>]
            #undef <var>
            #if <expr>
            #elif <expr>
            #else
            #endif
            #error <error string>
            #include "<file>"
          where <expr> is any valid Python expression.
        - The expression after #if/elif may be a Python statement. It is an
          error to refer to a variable that has not been defined by a -D
          option.
        - Special built-in methods for expressions:
            defined(varName)    Return true if given variable is defined.  
"""

import os
import sys
import getopt
import types
import re
import pprint


#---- exceptions

class PreprocessError(Exception):
    def __init__(self, errmsg, file=None, lineno=None, line=None):
        self.errmsg = str(errmsg)
        self.file = file
        self.lineno = lineno
        self.line = line
        Exception.__init__(self, errmsg, file, lineno, line)
    def __str__(self):
        s = ""
        if self.file is not None:
            s += self.file + ":"
        if self.lineno is not None:
            s += str(self.lineno) + ":"
        if self.file is not None or self.lineno is not None:
            s += " "
        s += self.errmsg
        #if self.line is not None:
        #    s += ": " + self.line
        return s



#---- global data

_version_ = (0, 6, 1)

# Comment delimiter info.
#   A mapping of content type to a list of 2-tuples defining the line
#   prefix and suffix for a comment.
_commentInfo = {
    "Python": [ ('#', '') ],
    "Perl": [ ('#', '') ],
    "Fortran90": [ ('!', '') ],
    "Tcl": [ ('#', '') ],
    "XML": [ ('<!--', '-->') ],
    "HTML": [ ('<!--', '-->') ],
    "Makefile": [ ('#', '') ],
    "JavaScript": [ ('/*', '*/'), ('//', '') ],
    "CSS": [ ('/*', '*/') ],
    "C": [ ('/*', '*/') ],
    "C++": [ ('/*', '*/'), ('//', '') ],
    "IDL": [ ('/*', '*/'), ('//', '') ],
}



#---- internal logging facility

class _Logger:
    DEBUG, INFO, WARN, ERROR, CRITICAL = range(5)
    def __init__(self, name, level=None, streamOrFileName=sys.stderr):
        self._name = name
        if level is None:
            self._level = self.WARN
        else:
            self._level = level
        if type(streamOrFileName) == types.StringType:
            self.stream = open(streamOrFileName, 'w')
            self._opennedStream = 1
        else:
            self.stream = streamOrFileName
            self._opennedStream = 0
    def __del__(self):
        if self._opennedStream:
            self.stream.close()
    def getLevel(self):
        return self._level
    def setLevel(self, level):
        self._level = level
    def _getLevelName(self, level):
        levelNameMap = {
            self.DEBUG: "DEBUG",
            self.INFO: "INFO",
            self.WARN: "WARN",
            self.ERROR: "ERROR",
            self.CRITICAL: "CRITICAL",
        }
        return levelNameMap[level]
    def log(self, level, msg, *args):
        if level < self._level:
            return
        message = "%s:%s: " % (self._name, self._getLevelName(level).lower())
        message = message + (msg % args) + "\n"
        self.stream.write(message)
        self.stream.flush()
    def debug(self, msg, *args):
        self.log(self.DEBUG, msg, *args)
    def info(self, msg, *args):
        self.log(self.INFO, msg, *args)
    def warn(self, msg, *args):
        self.log(self.WARN, msg, *args)
    def error(self, msg, *args):
        self.log(self.ERROR, msg, *args)
    def fatal(self, msg, *args):
        self.log(self.CRITICAL, msg, *args)

if 1:
    log = _Logger("preprocess", _Logger.WARN)
else:
    log = _Logger("preprocess", _Logger.DEBUG)



#---- internal support stuff

def _evaluate(expr, defines):
    """Evaluate the given expression string with the given context.

    XXX WARNING: This runs eval() on a user string. This is unsafe.
    """
    #interpolated = _interpolate(s, defines)
    try:
        rv = eval(expr, {'defined':lambda v: v in defines}, defines)
    except Exception, ex:
        msg = str(ex)
        if msg.startswith("name '") and msg.endswith("' is not defined"):
            # A common error (at least this is presumed:) is to have
            #   defined(FOO)   instead of   defined('FOO')
            # We should give a little as to what might be wrong.
            # msg == "name 'FOO' is not defined"  -->  varName == "FOO"
            varName = msg[len("name '"):-len("' is not defined")]
            if expr.find("defined(%s)" % varName) != -1:
                # "defined(FOO)" in expr instead of "defined('FOO')"
                msg += " (perhaps you want \"defined('%s')\" instead of "\
                       "\"defined(%s)\")" % (varName, varName)
        elif msg.startswith("invalid syntax"):
            msg = "invalid syntax: '%s'" % expr
        raise PreprocessError(msg, defines['__FILE__'], defines['__LINE__'])
    log.debug("evaluate %r -> %s (defines=%r)", expr, rv, defines)
    return rv


#---- content type determination
# (This is adpated from my 'check' app.)

def _getContentTypesFile():
    dname = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(dname, "content.types")

def _getContentTypesRegistry(filename=None):
    """Return the registry for the given content.types file.
   
    "filename" can optionally be used to specify a content.types file.
        Otherwise the default content.types file is used.
   
    The registry is three mappings:
        <suffix> -> <content type>
        <regex> -> <content type>
        <filename> -> <content type>
    """
    if filename is None:
        filename = _getContentTypesFile()

    suffixMap = {}
    regexMap = {}
    filenameMap = {}
    log.debug('load content types file: %r' % filename)
    try:
        fin = open(filename)
    except IOError:
        return
    while 1:
        line = fin.readline()
        if not line: break
        words = line.split()
        for i in range(len(words)):
            if words[i][0] == '#':
                del words[i:]
                break
        if not words: continue
        contentType, patterns = words[0], words[1:]
        if not patterns:
            if line[-1] == '\n': line = line[:-1]
            raise PreprocessError("bogus content.types line, there must "\
                                  "be one or more patterns: '%s'" % line)
        for pattern in patterns:
            if pattern.startswith('.'):
                if sys.platform.startswith("win"):
                    # Suffix patterns are case-insensitive on Windows.
                    pattern = pattern.lower()
                suffixMap[pattern] = contentType
            elif pattern.startswith('/') and pattern.endswith('/'):
                regexMap[re.compile(pattern[1:-1])] = contentType
            else:
                filenameMap[pattern] = contentType
    fin.close()
    return suffixMap, regexMap, filenameMap

def getContentType(filename):
    """Return a content type for the given filename.

    'check' maintains its own registry of content types similar to
    mime.types registries. See "check.types".  Returns None is no
    content type can be determined.
    """
    suffixMap, regexMap, filenameMap = _getContentTypesRegistry()
    basename = os.path.basename(filename)
    contentType = None
    # Try to determine from the filename.
    if not contentType and filenameMap.has_key(basename):
        contentType = filenameMap[basename]
        log.debug("Content type of '%s' is '%s' (determined from full "\
                  "filename).", filename, contentType)
    # Try to determine from the suffix.
    if not contentType and '.' in basename:
        suffix = "." + basename.split(".")[-1]
        if sys.platform.startswith("win"):
            # Suffix patterns are case-insensitive on Windows.
            suffix = suffix.lower()
        if suffixMap.has_key(suffix):
            contentType = suffixMap[suffix]
            log.debug("Content type of '%s' is '%s' (determined from "\
                      "suffix '%s').", filename, contentType, suffix)
    # Try to determine from the registered set of regex patterns.
    if not contentType:
        for regex, ctype in regexMap.items():
            if regex.search(basename):
                contentType = ctype
                log.debug("Content type of '%s' is '%s' (matches regex '%s')",
                          filename, contentType, regex.pattern)
                break
    # Try to determine from the file contents.
    # XXX reading shebang line/magic number
    # XXX reading Emacs-style mode line???
    # XXX should this be higher?
    # XXX should the contentType (if XML, say) be FURTHER scoped down
    return contentType



#---- module API

def preprocess(infile, outfile=sys.stdout, defines={}, force=0, keepLines=0,
               includePath=[], substitute=0, __preprocessedFiles=None):
    """Preprocess the given file.

    "infile" is the input filename.
    "outfile" is the output filename or stream (default is sys.stdout).
    "defines" is a dictionary of defined variables that will be
        understood in preprocessor statements. Keys must be strings and,
        currently, only the truth value of any key's value matters.
    "force" will overwrite the given outfile if it already exists. Otherwise
        an IOError will be raise if the outfile already exists.
    "keepLines" will cause blank lines to be emitted for preprocessor lines
        and content lines that would otherwise be skipped.
    "includePath" is a list of directories to search for given #include
        directives. The directory of the file being processed is presumed.
    "substitute", if true, will allow substitution of defines into emitted
        lines. (NOTE: This substitution will happen within program strings
        as well. This may not be what you expect.)
    "__preprocessedFiles" (for internal use only) is used to ensure files
        are not recusively preprocessed.

    Returns the modified dictionary of defines or raises PreprocessError if
    there was some problem.
    """
    if __preprocessedFiles is None: __preprocessedFiles = []
    log.info("preprocess(infile=%r, outfile=%r, defines=%r, force=%r, "\
             "keepLines=%r, includePath=%r, __preprocessedFiles=%r)",
             infile, outfile, defines, force, keepLines, includePath,
             __preprocessedFiles)
    absInfile = os.path.normpath(os.path.abspath(infile))
    if absInfile in __preprocessedFiles:
        raise PreprocessError("detected recursive #include of '%s'"\
                              % infile)
    __preprocessedFiles.append(os.path.abspath(infile))

    # Determine the content type of the input file.
    contentType = getContentType(infile)
    if contentType is None:
        raise PreprocessError("could not determine content type", infile)

    # Generate statement parsing regexes. Basic format:
    #       <comment-prefix> <preprocessor-stmt> <comment-suffix>
    #  Examples:
    #       <!-- #if foo -->
    #       ...
    #       <!-- #endif -->
    #
    #       # #if BAR
    #       ...
    #       # #else
    #       ...
    #       # #endif
    stmts = ['#\s*(?P<op>if|elif|ifdef|ifndef)\s+(?P<expr>.*?)',
             '#\s*(?P<op>else|endif)',
             '#\s*(?P<op>error)\s+(?P<error>.*?)',
             '#\s*(?P<op>define)\s+(?P<var>[^\s]*?)(\s+(?P<val>.+?))?',
             '#\s*(?P<op>undef)\s+(?P<var>[^\s]*?)',
             '#\s*(?P<op>include)\s+"(?P<fname>.*?)"',
            ]
    patterns = ['^\s*%s\s*%s\s*%s\s*$'\
                % (re.escape(ci[0]), stmt, re.escape(ci[1]))\
                for ci in _commentInfo[contentType]\
                for stmt in stmts]
    stmtRes = [re.compile(p) for p in patterns]
    
    # Process the input file.
    # (Would be helpful if I knew anything about lexing and parsing
    # simple grammars.)
    fin = open(infile, 'r')
    if type(outfile) in types.StringTypes:
        if force and os.path.exists(outfile):
            os.chmod(outfile, 0777)
            os.remove(outfile)
        fout = open(outfile, 'w')
    else:
        fout = outfile

    defines['__FILE__'] = infile
    SKIP, EMIT = range(2) # states
    states = [(EMIT,   # a state is (<emit-or-skip-lines-in-this-section>,
               0,      #             <have-emitted-in-this-if-block>,
               0)]     #             <have-seen-else-in-this-if-block>)
    lineNum = 0
    for line in fin.readlines():
        lineNum += 1
        log.debug("line %d: %r", lineNum, line)
        defines['__LINE__'] = lineNum

        # Is this line a preprocessor stmt line?
        #XXX Could probably speed this up by optimizing common case of
        #    line NOT being a preprocessor stmt line.
        for stmtRe in stmtRes:
            match = stmtRe.match(line)
            if match:
                break
        else:
            match = None

        if match:
            op = match.group("op")
            log.debug("%r stmt (states: %r)", op, states)
            if op == "define":
                if states and states[-1][0] == SKIP: continue
                var, val = match.group("var", "val")
                if val is None:
                    val = None
                else:
                    try:
                        val = eval(val, {}, {})
                    except:
                        pass
                defines[var] = val
            elif op == "undef":
                if states and states[-1][0] == SKIP: continue
                var = match.group("var")
                try:
                    del defines[var]
                except KeyError:
                    pass
            elif op == "include":
                if states and states[-1][0] == SKIP: continue
                f = match.group("fname")
                for d in [os.path.dirname(infile)] + includePath:
                    fname = os.path.normpath(os.path.join(d, f))
                    if os.path.exists(fname):
                        break
                else:
                    raise PreprocessError("could not find #include'd file "\
                                          "\"%s\" on include path: %r"\
                                          % (f, includePath))
                defines = preprocess(fname, outfile, defines, force,
                                     keepLines, includePath, substitute,
                                     __preprocessedFiles)
            elif op in ("if", "ifdef", "ifndef"):
                if op == "if":
                    expr = match.group("expr")
                elif op == "ifdef":
                    expr = "defined('%s')" % match.group("expr")
                elif op == "ifndef":
                    expr = "not defined('%s')" % match.group("expr")
                try:
                    if _evaluate(expr, defines):
                        states.append((EMIT, 1, 0))
                    else:
                        states.append((SKIP, 0, 0))
                except KeyError:
                    raise PreprocessError("use of undefined variable in "\
                                          "#%s stmt" % op, defines['__FILE__'],
                                          defines['__LINE__'], line)
            elif op == "elif":
                expr = match.group("expr")
                try:
                    if states[-1][2]: # already had #else in this if-block
                        raise PreprocessError("illegal #elif after #else in "\
                            "same #if block", defines['__FILE__'],
                            defines['__LINE__'], line)
                    elif states[-1][1]: # if have emitted in this if-block
                        states[-1] = (SKIP, 1, 0)
                    elif _evaluate(expr, defines):
                        states[-1] = (EMIT, 1, 0)
                    else:
                        states[-1] = (SKIP, 0, 0)
                except IndexError:
                    raise PreprocessError("#elif stmt without leading #if "\
                                          "stmt", defines['__FILE__'],
                                          defines['__LINE__'], line)
            elif op == "else":
                try:
                    if states[-1][2]: # already had #else in this if-block
                        raise PreprocessError("illegal #else after #else in "\
                            "same #if block", defines['__FILE__'],
                            defines['__LINE__'], line)
                    elif states[-1][1]: # if have emitted in this if-block
                        states[-1] = (SKIP, 1, 1)
                    else:
                        states[-1] = (EMIT, 1, 1)
                except IndexError:
                    raise PreprocessError("#else stmt without leading #if "\
                                          "stmt", defines['__FILE__'],
                                          defines['__LINE__'], line)
            elif op == "endif":
                try:
                    states.pop()
                except IndexError:
                    raise PreprocessError("#endif stmt without leading #if"\
                                          "stmt", defines['__FILE__'],
                                          defines['__LINE__'], line)
            elif op == "error":
                if states and states[-1][0] == SKIP: continue
                error = match.group("error")
                raise PreprocessError("#error: "+error, defines['__FILE__'],
                                      defines['__LINE__'], line)
            log.debug("states: %r", states)
            if keepLines:
                fout.write("\n")
        else:
            try:
                if states[-1][0] == EMIT:
                    log.debug("emit line (%s)" % states[-1][1])
                    # Substitute all defines into line.
                    # XXX Should avoid recursive substitutions. But that
                    #     would be a pain right now.
                    sline = line
                    if substitute:
                        for name, value in defines.items():
                            sline = sline.replace(name, str(value))
                    fout.write(sline)
                elif keepLines:
                    log.debug("keep blank line (%s)" % states[-1][1])
                    fout.write("\n")
                else:
                    log.debug("skip line (%s)" % states[-1][1])
            except IndexError:
                raise PreprocessError("superfluous #endif before this line",
                                      defines['__FILE__'],
                                      defines['__LINE__'])
    if len(states) > 1:
        raise PreprocessError("unterminated #if block", defines['__FILE__'],
                              defines['__LINE__'])
    elif len(states) < 1:
        raise PreprocessError("superfluous #endif on or before this line",
                              defines['__FILE__'], defines['__LINE__'])
    return defines


#---- mainline

def main(argv):
    try:
        optlist, args = getopt.getopt(argv[1:], 'hVvo:D:fkI:s',
            ['help', 'version', 'verbose', 'force', 'keep-lines',
             'substitute'])
    except getopt.GetoptError, msg:
        sys.stderr.write("preprocess: error: %s. Your invocation was: %s\n"\
                         % (msg, argv))
        sys.stderr.write("See 'preprocess --help'.\n")
        return 1
    outfile = sys.stdout
    defines = {}
    force = 0
    verbose = 0
    keepLines = 0
    substitute = 0
    includePath = []
    for opt, optarg in optlist:
        if opt in ('-h', '--help'):
            sys.stdout.write(__doc__)
            return 0
        elif opt in ('-V', '--version'):
            sys.stderr.write("Preprocess %s\n"\
                             % '.'.join([str(i) for i in _version_]))
            return 0
        elif opt in ('-v', '--verbose'):
            verbose = 1
        elif opt == '-o':
            outfile = optarg
        if opt in ('-f', '--force'):
            force = 1
        elif opt == '-D':
            if optarg.find('=') != -1:
                var, val = optarg.split('=', 1)
                try:
                    val = eval(val, {}, {})
                except:
                    pass
            else:
                var, val = optarg, None
            defines[var] = val
        elif opt in ('-k', '--keep-lines'):
            keepLines = 1
        elif opt == '-I':
            includePath.append(optarg)
        elif opt in ('-s', '--substitute'):
            substitute = 1

    if len(args) != 1:
        sys.stderr.write("preprocess: error: incorrect number of "\
                         "arguments: argv=%r\n" % argv)
        return 1
    else:
        infile = args[0]

    try:
        preprocess(infile, outfile, defines, force, keepLines, includePath,
                   substitute)
    except PreprocessError, ex:
        if verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        else:
            sys.stderr.write("preprocess: error: %s\n" % str(ex))

if __name__ == "__main__":
    __file__ = sys.argv[0]
    sys.exit( main(sys.argv) )

