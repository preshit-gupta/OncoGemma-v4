import threading

# Unified global lock across all endpoints (tiles, thumbnails, patches)
# to guarantee 100% thread-safety for OpenSlide native C library on Windows.
OPENSLIDE_GLOBAL_LOCK = threading.Lock()
