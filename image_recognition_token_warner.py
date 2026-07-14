import time
import os

_DEFAULT_LOG = "./logs/app.log"

def tail_log(filepath):
    """Generator that yields new lines added to the file."""
    with open(filepath, "r") as f:
        # Move to the end of the file initially
        f.seek(0, os.SEEK_END)

        while True:
            line = f.readline()
            if not line:
                # No new content, wait a bit and try again
                time.sleep(0.1)
                continue
            yield line


def monitor_cache_misses(filepath):
    """Counts 'Cache miss' occurrences in the log stream."""
    miss_count = 0
    print(f"Monitoring {filepath} for cache misses...")

    for line in tail_log(filepath):
        if "Cache miss" in line:
            miss_count += 1
            print(f"Cache miss detected! Total count: {miss_count}")
            if miss_count >= 10:
                print(f"Uh-oh!! A lot of new files were being inferred on! Big token use!!")
                # SEND MAIL!

if __name__ == "__main__":
    monitor_cache_misses(_DEFAULT_LOG)