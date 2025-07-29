from dataclasses import dataclass
from enum import Enum
import sys
from typing import List, Optional
from websocket import WebSocket, create_connection
from loguru import logger
import json
import requests
from bs4 import BeautifulSoup

logger.remove()  # remove the old handler. Else, the old one will work along with the new one you've added below'
logger.add(sys.stderr, level="INFO")

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
    url: str = STARTING_URL

    def __repr__(self):
        return (
            "--- LiveViewTokens ---\n"
            f"csrf_token -> {self.csrf_token}\n"
            f"topic -> {self.topic}\n"
            f"session -> {self.session}\n"
            f"static -> {self.static}\n"
            f"url -> {self.url}\n"
            "-----------------------"
        )


@dataclass
class ResponseMessage:
    _na: int
    id: int
    topic: str
    type: str
    status: str
    payload: dict
    success: bool = True

    @classmethod
    def pack(cls, response: List) -> "ResponseMessage":
        """
        Parse a response list into a ResponseMessage object.
        """
        if len(response) < 5:
            raise ValueError("Invalid response format")
        return ResponseMessage(
            _na=int(response[0]),
            id=int(response[1]),
            type=response[3],
            topic=response[2],
            status=response[4]["status"],
            payload=response[4]["response"] if "response" in response[4] else {},
        )

    def __repr__(self):
        return (
            f"--- ResponseMessage ---\n"
            f"_na -> {self._na}\n"
            f"id -> {self.id}\n"
            f"topic -> {self.topic}\n"
            f"status -> {self.status}\n"
            f"payload -> {self.payload}\n"
            "-----------------------"
        )


class MessageMaker:
    def __init__(self, id: int, tokens: LiveViewTokens):
        self.id = id
        self.tokens: LiveViewTokens = tokens

    def _base_msg(self):
        return ["4", str(self.id), self.tokens.topic]

    def heartbeat_msg(self):
        return json.dumps([None, "10", "phoenix", "heartbeat", {}])

    def join_msg(self):
        msg = self._base_msg()
        msg += [
            "phx_join",
            {
                "url": self.tokens.url,
                "params": {
                    "_csrf_token": self.tokens.csrf_token,
                    # "_track_static": [
                    #     "https://addapixel.fly.dev/assets/app-d66b8a37f953d50d4da432b3cb181d16.css?vsn=d",
                    #     "https://addapixel.fly.dev/assets/app-7a7c16399b1d24d1a7fed3df20921d38.js?vsn=d",
                    # ],
                    "_mounts": 0,
                    "_mount_attempts": 0,
                },
                "session": self.tokens.session,
                "static": self.tokens.static,
                "sticky": False,
            },
        ]
        return json.dumps(msg)

    def select_color_msg(self, color: int):
        msg = self._base_msg()
        msg += [
            "event",
            {
                "type": "click",
                "event": "select_color",
                "value": {"idx": str(color), "value": ""},
            },
        ]
        return json.dumps(msg)

    def select_pixel_msg(self, x: int, y: int):
        msg = self._base_msg()
        msg += [
            "event",
            {"type": "hook", "event": "pixel_click", "value": {"x": x, "y": y}},
        ]
        return json.dumps(msg)

    def save_pixel_msg(self):
        msg = self._base_msg()
        msg += ["event", {"type": "click", "event": "save", "value": {"value": ""}}]
        return json.dumps(msg)


class AddAPixelClient:
    def __init__(self, url: str, board_width: int, board_height: int):
        self.url = url
        self.id = 4  # Always starts at 4
        self.tokens: LiveViewTokens = None
        self.cookies: str = None
        self.colors: List[str] = []
        self.connection_str: str = None
        self.ws: WebSocket = None
        self.msg_maker = None
        self.board_size = {"x": board_width, "y": board_height}
        logger.info(
            f"Initialized AddAPixelClient with: \nURL -> {self.url}, \nBoard Size -> {self.board_size}"
        )

    def _extract_liveview_tokens(self):
        # Fetch the page
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Cache-Control": "no-cache",
        }
        session = requests.Session()
        response = session.get(self.url, headers=headers)
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

        color_elements = soup.select("li.color button[title]")
        colors = [btn["title"] for btn in color_elements]

        self.tokens = LiveViewTokens(
            csrf_token=csrf_token, topic=topic, session=session, static=static
        )
        self.cookies = cookie_header
        self.colors = colors

    def connect(self):
        self._extract_liveview_tokens()

        logger.debug(self.tokens)
        logger.debug(f"Cookies: {self.cookies}")
        logger.debug(f"Colors: {self.colors}")

        self.msg_maker = MessageMaker(self.id, self.tokens)

        self.connection_str = CONNECTION_STRING.format(self.tokens.csrf_token)
        self.ws = create_connection(
            self.connection_str,
            header=[
                f"Cookie: {self.cookies}",
                "User-Agent: Mozilla/5.0",  # optional, but helpful
                "Origin: https://addapixel.fly.dev",
            ],
        )
        logger.info("Connected to WebSocket!")

    def join_channel(self) -> bool:
        response = self._send_and_receive(self.msg_maker.join_msg())
        if response.status != "ok":
            logger.error("Failed to join channel or get response status.")
        logger.info(f"Joined channel successfully!")
        return True

    def _extract_color_palette(self, response):
        """
        Fetch the color palette from the server.
        """
        logger.info(f"Color palette response: {response}")

    def write_pixel(self, x: int, y: int, color: Colors):
        self.ws.send(self.msg_maker.select_color_msg(color.value))
        self.ws.send(self.msg_maker.select_pixel_msg(x, y))
        self.ws.send(self.msg_maker.save_pixel_msg())
        self.id += 3

    def heartbeat(self):
        self.ws.send(self.msg_maker.heartbeat_msg())
        self.get_response()
        self.id += 1

    def get_response(self) -> List:
        response = self.ws.recv()
        return json.loads(response)

    def get_response_status(self) -> Optional[str]:
        response = self.ws.recv()
        try:
            status = json.loads(response)[4]["status"]
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return None
        return status

    def _send_and_receive(self, message: str) -> ResponseMessage:
        """
        Send a message and wait for a response.
        """
        self.ws.send(message)
        response = self.ws.recv()
        return ResponseMessage.pack(json.loads(response))

    # Context manager for automatic connection handling
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.ws.close()
        logger.info("WebSocket connection closed.")
