import sys
import threading
import time
from typing import Dict
from loguru import logger
from PIL import Image
import numpy as np
from .lib import TRANSPARENT_COLOR_ID, AddAPixelClient, ColorPalette
from tqdm import tqdm

STARTING_URL = "https://addapixel.fly.dev/#0:0:1.0"
BOARD_WIDTH = 4095
BOARD_HEIGHT = 2303

logger.remove()  # remove the old handler. Else, the old one will work along with the new one you've added below'
logger.add(sys.stderr, level="INFO")


def image_to_color_array(image_path: str, color_palette: ColorPalette) -> np.ndarray:
    """
    Convert an image to a binary array based on a threshold.
    Pixels above the threshold are set to 1 (white), below are set to 0 (black).
    """
    img = Image.open(image_path)
    # For every pixel lookup color id and put into array at that index
    unmatched_pixels, trans_pixels = 0, 0
    total_pixels = img.width * img.height
    color_array = np.zeros((img.height, img.width), dtype=int)
    for y in range(img.height):
        for x in range(img.width):
            pixel = img.getpixel((x, y))
            hex_color = "#{:02X}{:02X}{:02X}".format(*pixel[:3])  # uppercase hex
            color_id = color_palette.get_color_id_from_hexcode(hex_color)
            if color_id == TRANSPARENT_COLOR_ID:
                trans_pixels += 1
            if color_id is not None:
                color_array[y, x] = color_id
            else:
                unmatched_pixels += 1
                color_array[y, x] = 0
    logger.warning(
        f"{unmatched_pixels}/{total_pixels} | {unmatched_pixels / total_pixels * 100:.2f}% pixels couldn't be matched to the palette."
    )
    logger.warning(
        f"{trans_pixels}/{total_pixels} | {trans_pixels / total_pixels * 100:.2f}% of pixels are transparent..."
    )

    return color_array


def send_pixels_thread(
    start_y: int,
    end_y: int,
    color_array: np.ndarray,
    start_offset: Dict,
    sleep_per_pixel_s: float,
    sleep_per_row_s: float,
    url: str,
):
    with AddAPixelClient(url, BOARD_WIDTH, BOARD_HEIGHT) as client:
        total_pixels = (end_y - start_y) * color_array.shape[1]
        with tqdm(total=total_pixels) as pbar:
            for y in range(start_y, end_y):
                if y < 0 or y >= color_array.shape[0]:
                    continue
                for x in range(color_array.shape[1]):
                    if x < 0 or x >= color_array.shape[1]:
                        continue
                    color_id = color_array[y, x]
                    if color_id != TRANSPARENT_COLOR_ID:
                        client.write_pixel(
                            x + start_offset["x"], y + start_offset["y"], color_id
                        )
                        time.sleep(sleep_per_pixel_s)
                    pbar.update(1)
                time.sleep(sleep_per_row_s)


if __name__ == "__main__":
    ## CONFIGS
    start_offset = {"x": 3344, "y": -37}
    start_row = 0
    image_path = "what-u-got.png"  # Replace with your image path
    n_threads = 20
    sleep_per_px = 0.1
    sleep_per_row = 1

    logger.info("Processing image to send...")
    color_palette = ColorPalette.pack(STARTING_URL)
    logger.info(f"Color palette loaded with {len(color_palette.colors)} colors.")

    color_array = image_to_color_array(image_path, color_palette)
    logger.info(f"Color array shape: {color_array.shape}")

    threads = []
    n_rows = color_array.shape[0] // n_threads
    total_non_trans_pixels = np.count_nonzero(color_array != TRANSPARENT_COLOR_ID)
    total_seconds = (
        (((total_non_trans_pixels * sleep_per_px)) + (n_rows * sleep_per_row))
        / n_threads
    ) * 1.1

    logger.warning(
        f"Do you want to send {total_non_trans_pixels} pixels w/ {n_threads} threads. This will take approx {total_seconds/60:.1f} mins"
    )
    input(f"Press Enter to continue...")

    for i in range(n_threads):
        start_y = i * n_rows
        # Last thread takes the remainder
        end_y = (i + 1) * n_rows if i < n_threads - 1 else color_array.shape[0]
        t = threading.Thread(
            target=send_pixels_thread,
            args=(
                start_y,
                end_y,
                color_array,
                start_offset,
                sleep_per_px,
                sleep_per_row,
                STARTING_URL,
            ),
        )
        t.start()
        threads.append(t)

    # Wait for all threads to finish
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        logger.error("Process interrupted by user.")
        # Close all threads gracefully
        for t in threads:
            if t.is_alive():
                logger.warning(
                    f"Thread {t.name} is still running, attempting to close it."
                )
                t.join(timeout=1)
        logger.info("All threads have been closed.")
        logger.info("Exiting program.")

    # addapixel_client = AddAPixelClient(
    #     STARTING_URL, BOARD_WIDTH, BOARD_HEIGHT
    # )  # Create Client

    # # Testing connection
    # with addapixel_client as client:
    #     success = client.join_channel()
    #     if not success:
    #         sys.exit(1)
    #     client.heartbeat()

    #     input("Press Enter to start sending pixels...")

    #     logger.info("Sending Pixels starting at offset: {start_offset}")
    #     rows = start_row
    #     for y in range(start_row, color_array.shape[0]):
    #         for x in range(color_array.shape[1]):
    #             color_id = color_array[y, x]
    #             client.write_pixel(
    #                 x + start_offset["x"], y + start_offset["y"], color_id
    #             )
    #         logger.info(f"Row {y + 1}/{color_array.shape[0]} sent.")
    #         rows += 1
    #         if rows % 50 == 0:  # Log every 50 rows
    #             logger.info(f"Sent {rows} rows so far.")
    #             client.heartbeat()
    #             time.sleep(1)  # Sleep to avoid overwhelming the server
    #         time.sleep(0.1)  # Sleep to avoid overwhelming the server
