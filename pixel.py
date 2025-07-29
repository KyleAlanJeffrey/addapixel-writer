from dataclasses import dataclass
from enum import Enum
import time
from websocket import create_connection
from loguru import logger
import json
import requests
from bs4 import BeautifulSoup

from PIL import Image
import numpy as np

# wss://addapixel.fly.dev/live/websocket?_csrf_token=DhE9PDMhFUk4FwdzJgk1cic-SBoVUHAldZXEdrwqrUE1bpG1qh8vo3DD&_track_static%5B0%5D=https%3A%2F%2Faddapixel.fly.dev%2Fassets%2Fapp-d66b8a37f953d50d4da432b3cb181d16.css%3Fvsn%3Dd&_track_static%5B1%5D=https%3A%2F%2Faddapixel.fly.dev%2Fassets%2Fapp-7a7c16399b1d24d1a7fed3df20921d38.js%3Fvsn%3Dd&_mounts=0&_mount_attempts=0&_live_referer=undefined&vsn=2.0.0

STARTING_URL = "https://addapixel.fly.dev/#0:0:1.0"
BASE_URL = "addapixel.fly.dev/live/websocket"
CONNECTION_STRING = "wss://addapixel.fly.dev/live/websocket?_csrf_token={}&_mounts=0&_mount_attempts=0&_live_referer=undefined&vsn=2.0.0"


class Colors(Enum):
    BLACK = 0
    WHITE = 1


@dataclass
class LiveViewTokens:
    csrf_token: str
    topic: str
    session: str
    static: str


def extract_liveview_tokens(url: str) -> LiveViewTokens:
    # Fetch the page
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Cache-Control": "no-cache",
    }
    session = requests.Session()
    response = session.get(url, headers=headers)
    cookies = session.cookies.get_dict()
    cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])

    html = response.text
    # Save the HTML to a file for debugging
    with open("page.html", "w", encoding="utf-8") as f:
        f.write(html)

    # Parse with BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Get CSRF token from <meta> tag
    csrf_meta = soup.find("meta", attrs={"name": "csrf-token"})
    csrf_token = csrf_meta["content"] if csrf_meta else None

    # Find the LiveView root div (with id like "phx-...")
    liveview_div = soup.find("div", id=lambda x: x and x.startswith("phx-"))

    if liveview_div:
        topic = f"lv:{liveview_div['id']}"
        session = liveview_div.get("data-phx-session")
        static = liveview_div.get("data-phx-static")
    else:
        topic = session = static = None

    return (
        LiveViewTokens(
            csrf_token=csrf_token, topic=topic, session=session, static=static
        ),
        cookie_header,
    )


def heartbeat_msg():
    return json.dumps([None, "10", "phoenix", "heartbeat", {}])


def BaseMessage(id: int, topic: str):
    return ["4", str(id), topic]


def JoinMessage(id: int, tokens: LiveViewTokens):
    msg = BaseMessage(id, tokens.topic)
    msg += [
        "phx_join",
        {
            "url": STARTING_URL,
            "params": {
                "_csrf_token": tokens.csrf_token,
                # "_track_static": [
                #     "https://addapixel.fly.dev/assets/app-d66b8a37f953d50d4da432b3cb181d16.css?vsn=d",
                #     "https://addapixel.fly.dev/assets/app-7a7c16399b1d24d1a7fed3df20921d38.js?vsn=d",
                # ],
                "_mounts": 0,
                "_mount_attempts": 0,
            },
            "session": tokens.session,
            "static": tokens.static,
            "sticky": False,
        },
    ]
    return json.dumps(msg)


def SelectColorMessage(id: int, tokens: LiveViewTokens, color: int):
    msg = BaseMessage(id, tokens.topic)
    msg += [
        "event",
        {
            "type": "click",
            "event": "select_color",
            "value": {"idx": str(color), "value": ""},
        },
    ]
    return json.dumps(msg)


def SelectPixelMessage(id: int, tokens: LiveViewTokens, x: int, y: int):
    msg = BaseMessage(id, tokens.topic)
    msg += [
        "event",
        {"type": "hook", "event": "pixel_click", "value": {"x": x, "y": y}},
    ]
    return json.dumps(msg)


def SavePixelMessage(id: int, tokens: LiveViewTokens):
    msg = BaseMessage(id, tokens.topic)
    msg += ["event", {"type": "click", "event": "save", "value": {"value": ""}}]
    return json.dumps(msg)


def send_and_receive(ws, msg, print_response=False):
    ws.send(msg)
    response = json.loads(ws.recv())
    if print_response:
        logger.info(f"Sent {json.loads(msg)[3]} | received: {response}")
    return response


def write_pixel(ws, tokens: LiveViewTokens, x: int, y: int, color: Colors, id: int):
    send_and_receive(ws, SelectColorMessage(id, tokens, color.value), True)
    send_and_receive(ws, SelectPixelMessage(id, tokens, x, y), True)
    send_and_receive(ws, SavePixelMessage(id, tokens))
    return id + 3


if __name__ == "__main__":
    ######################## LOAD IMAGE ########################
    logger.critical("Loading Image into pixel array...")
    # Load the image
    img = Image.open("img.png").convert("L")  # Convert to grayscale

    # Convert to numpy array
    img_array = np.array(img)

    # Apply threshold (e.g., anything >128 is white = 1)
    threshold = 128
    binary_array = (img_array > threshold).astype(int)

    print(binary_array)



    ######################## CONNECT TO WEBSOCKET ########################
    logger.critical("Starting pixel game client...")
    tokens, cookies = extract_liveview_tokens(STARTING_URL)
    logger.debug(f"Extracted tokens: {tokens} and cookies: {cookies}")
    connection_str = CONNECTION_STRING.format(tokens.csrf_token)

    logger.info(f"Connecting to {connection_str}...")
    ws = create_connection(
        connection_str,
        header=[
            f"Cookie: {cookies}",
            "User-Agent: Mozilla/5.0",  # optional, but helpful
            "Origin: https://addapixel.fly.dev",
        ],
    )
    logger.info("Connected to WebSocket!")

    id = 4  # Always starts at 4
    send_and_receive(ws, JoinMessage(id, tokens))
    result = send_and_receive(ws, heartbeat_msg(), True)
    id = int(result[1])
    id += 1

    ###################### WRITE PIXELS ######################
    input("Press Enter to start sending pixels...")
    start_offset = {"x": 3000, "y": 0}
    logger.critical("Sending Pixels starting at offset: {start_offset}")
    for y in range(binary_array.shape[0]):
        for x in range(binary_array.shape[1]):
            if binary_array[y, x] == 1:
                id = write_pixel(ws, tokens, start_offset["x"] + x, start_offset["y"] + y, Colors.WHITE, id)
            else:
                id = write_pixel(ws, tokens, start_offset["x"] + x, start_offset["y"] + y, Colors.BLACK, id)
        time.sleep(1)

    ws.close()

# logger.info("Joining channel...")
# result = send_and_receive(ws, join_msg())
# print(result)

# result = send_and_receive(ws, heartbeat_msg())

# id = int(result[1])
# logger.info(f"Received id: {id}")


# logger.info("Responses:")
# for response in responses:
#     logger.info(response)
