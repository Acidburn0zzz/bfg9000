#ifndef INC_MIDDLE_HPP
#define INC_MIDDLE_HPP

#if defined(_WIN32) && !defined(LIBMIDDLE_STATIC)
#  ifdef LIBMIDDLE_EXPORTS
#    define LIBMIDDLE_PUBLIC __declspec(dllexport)
#  else
#    define LIBMIDDLE_PUBLIC __declspec(dllimport)
#  endif
#else
#  define LIBMIDDLE_PUBLIC
#endif

namespace middle {
  void LIBMIDDLE_PUBLIC hello();
}

#endif
