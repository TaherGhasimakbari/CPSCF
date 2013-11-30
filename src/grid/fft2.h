#ifndef FFT2_H
#define FFT2_H

/*
* PSCF - Polymer Self-Consistent Field Theory
* Copyright (2013) David C. Morse
* email: morse@cems.umn.edu
*
* This program is a free software; you can redistribute it and/or modify
* it under the terms of the GNU General Public License as published by
* the Free Software Foundation. A copy of this license is included in
* the LICENSE file in the top-level PSCF directory. 
*
* This is a C++ wrapper class for fftw2 package.
*/

   class fft2
   {

   public:

   /**
   * constructor.
   */
   fft2(int ngrid[3]);

   /**
   * destructor.
   */
   ~fft2();
 
   /**
   * creating fftw plan.
   */
   void create_fft_plan();

   /**
   * fft calculator. Forward and Inverse fft for 1, 2, or 3D depending on direction!
   */
   fftw_complex fft(fftw_complex in);  

   /**
   * complex fft calculator. Forward and Inverse fft for 1, 2, or 3D depending on direction!
   */
   fftw_complex fftc(fftw_complex in)
   
   private:
   /**
   * fftw flags.
   */
   fftw_complex *input_;
   fftw_complex *output_;
   fftw_plan plan_;

   int FFTW_FORWARD; 
   int FFTW_BACKWARD;
   int FFTW_REAL_TO_COMPLEX;
   int FFTW_COMPLEX_TO_REAL;
   int FFTW_ESTIMATE;
   int FFTW_MEASURE;
   int FFTW_OUT_OF_PLACE; 
   int FFTW_IN_PLACE;
   int FFTW_USE_WISDOM;
   int FFTW_THREADSAFE;

}
#endif
