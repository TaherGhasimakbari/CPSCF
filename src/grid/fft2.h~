#ifndef FFT2_H
#define FFT2_H

/*
* PSCF - Polymer Self-Consistent Field Theory
* Copyright (2007) David C. Morse
* email: morse@cems.umn.edu
*
* This program is free software; you can redistribute it and/or modify
* it under the terms of the GNU General Public License as published by
* the Free Software Foundation. A copy of this license is included in
* the LICENSE file in the top-level PSCF directory. 
*
* C++ wrapper class for fftw2 package
*/

   class fft2
   {

   /**
   * fft_plan structure.
   */
   struct fft_plan{
      int     n[3]                                                  // grid dimensions, 0 for unused dimensions
      double  f                                                     // fftw plan object for forward transform
      double  r                                                     // fftw plan object for inverse transform
   };

   public:

   /**
   * constructor.
   */
   fft2(int = -1,
        int = +1,
        int = -1,
        int = +1,
        int =  0,
        int = +1,
        int =  0,
        int =  8,
        int = 16,
        int = 128);

   /**
   * destructor.
   */
   ~fft2();
 
   /**
   * creating fftw plan.
   */
   void create_fft_plan(int ngrid[], bool fft_c2c);

   /**
   * fft calculator. Forward FFT for 1, 2, or 3D
   */
   complex DArray fft(DArray in);

   /**
   * inverse fft calculator. Inverse FFT for 1, 2, or 3D
   */
   DArray ifft(complex DArray in);                                          

   /**
   * inverse fft calculator. Complex FFT for 1, 2, or 3D
   */
   complex DArray fftc(complex DArray in, int direction)

   /**
   * complex fft calculator. Complex FFT for 1, 2, or 3D
   */
   complex DArray fftc(complex DArray in, int direction)
   
   private:
   /**
   * Parameters required by fftw.
   */
   const int FFTW_FORWARD; 
   const int FFTW_BACKWARD;
   const int FFTW_REAL_TO_COMPLEX;
   const int FFTW_COMPLEX_TO_REAL;
   const int FFTW_ESTIMATE;
   const int FFTW_MEASURE;
   const int FFTW_OUT_OF_PLACE; 
   const int FFTW_IN_PLACE;
   const int FFTW_USE_WISDOM;
   const int FFTW_THREADSAFE;

}
#endif
