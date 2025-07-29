import sys
from loguru import logger
from PIL import Image
import numpy as np
from .lib import AddAPixelClient, Colors

STARTING_URL = "https://addapixel.fly.dev/#0:0:1.0"
BOARD_WIDTH = 4095
BOARD_HEIGHT = 2303

logger.remove()  # remove the old handler. Else, the old one will work along with the new one you've added below'
logger.add(sys.stderr, level="INFO")


def image_to_binary_array(image_path: str, threshold: int = 128) -> np.ndarray:
    """
    Convert an image to a binary array based on a threshold.
    Pixels above the threshold are set to 1 (white), below are set to 0 (black).
    """
    img = Image.open(image_path).convert("L")  # Convert to grayscale
    img_array = np.array(img)
    binary_array = (img_array > threshold).astype(int)
    return binary_array


if __name__ == "__main__":
    ######################## LOAD IMAGE ########################
    logger.info("Loading Image into pixel array...")
    image_path = "img.png"  # Replace with your image path
    binary_array = image_to_binary_array(image_path)

    addapixel_client = AddAPixelClient(
        STARTING_URL, BOARD_WIDTH, BOARD_HEIGHT
    )  # Create Client
    with addapixel_client as client:
        client.join_channel()
        response = client.get_response_status()
        if response is None:
            logger.error("Failed to join channel or get response status.")
            sys.exit(1)
        logger.info(f"Joined channel w/ response: {response}")
        client.heartbeat()

    input("Press Enter to start sending pixels...")

    start_offset = {"x": 3000, "y": 0}
    logger.info("Sending Pixels starting at offset: {start_offset}")
    with addapixel_client as client:
        for y in range(binary_array.shape[0]):
            for x in range(binary_array.shape[1]):
                if binary_array[y, x] == 1:
                    id = client.write_pixel(
                        start_offset["x"] + x,
                        start_offset["y"] + y,
                        Colors.WHITE,
                        id,
                    )
                else:
                    id = client.write_pixel(
                        start_offset["x"] + x,
                        start_offset["y"] + y,
                        Colors.BLACK,
                        id,
                    )
