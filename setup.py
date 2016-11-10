from distutils.core import setup
from Cython.Build import cythonize
import numpy
import os

os.environ["CPPFLAGS"] = os.getenv("CPPFLAGS", "") + "-I" + numpy.get_include() 
setup(ext_modules = cythonize("samplerbox_audio.pyx"), include_dirs=[numpy.get_include()])