import sys
import time
from loguru import logger
from PIL import Image
import numpy as np
from .lib import AddAPixelClient, Colors

STARTING_URL = "https://addapixel.fly.dev/#0:0:1.0"
BOARD_WIDTH = 4095
BOARD_HEIGHT = 2303

logger.remove()  # remove the old handler. Else, the old one will work along with the new one you've added below'
logger.add(sys.stderr, level="INFO")


def image_to_color_array(image_path: str) -> np.ndarray:
    """
    Convert an image to a binary array based on a threshold.
    Pixels above the threshold are set to 1 (white), below are set to 0 (black).
    """
    img = Image.open(image_path)
    # For every pixel lookup color id and put into array at that index
    color_array = np.zeros((img.height, img.width), dtype=int)
    for y in range(img.height):
        for x in range(img.width):
            pixel = img.getpixel((x, y))
            hex_color = "#{:02X}{:02X}{:02X}".format(*pixel[:3])  # uppercase hex
            color_id = client.get_color_id(hex_color)
            if color_id is not None:
                color_array[y, x] = color_id
    return color_array


if __name__ == "__main__":

    addapixel_client = AddAPixelClient(
        STARTING_URL, BOARD_WIDTH, BOARD_HEIGHT
    )  # Create Client

    # Testing connection
    with addapixel_client as client:
        success = client.join_channel()
        logger.info(f"Color palette: {client.colors}")
        if not success:
            sys.exit(1)
        client.heartbeat()

        ######################## LOAD IMAGE ########################
        logger.info("Loading Image into pixel array...")
        image_path = "earthly-delights.png"  # Replace with your image path
        color_array = image_to_color_array(image_path)
        logger.info(f"Color array shape: {color_array.shape}")

        input("Press Enter to start sending pixels...")
        start_offset = {"x": 1873, "y": 1348}
        start_row = 600

        logger.info("Sending Pixels starting at offset: {start_offset}")
        rows = start_row
        for y in range(start_row, color_array.shape[0]):
            for x in range(color_array.shape[1]):
                color_id = color_array[y, x]
                client.write_pixel(
                    x + start_offset["x"], y + start_offset["y"], color_id
                )
            logger.info(f"Row {y + 1}/{color_array.shape[0]} sent.")
            rows += 1
            if rows % 50 == 0:  # Log every 40 rows
                logger.info(f"Sent {rows} rows so far.")
                client.heartbeat()
                time.sleep(1)  # Sleep to avoid overwhelming the server
            time.sleep(0.1)  # Sleep to avoid overwhelming the server
