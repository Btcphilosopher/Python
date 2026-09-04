cursor-automation/
├── engine/
│   ├── __init__.py
│   ├── core.py
│   ├── cursor.py
│   ├── keyboard.py
│   ├── browser.py
│   ├── workflow.py
│   ├── scheduler.py
│   ├── vision.py
│   ├── safety.py
│   ├── recorder.py
│   ├── telemetry.py
│   └── config.py
├── workflows/
├── screenshots/
├── tests/
├── requirements.txt
└── main.py
requirements.txt
pyautogui>=0.9.54
playwright>=1.50.0
Pillow>=11.0.0
opencv-python>=4.10.0
pydantic>=2.10.0
engine/config.py
from pydantic import BaseModel, Field


class SafetyConfig(BaseModel):
    max_actions: int = 1000
    action_delay: float = 0.05
    fail_safe: bool = True
    screenshot_on_error: bool = True


class CursorConfig(BaseModel):
    move_duration: float = 0.15
    tween: str = "easeInOutQuad"


class BrowserConfig(BaseModel):
    headless: bool = False
    timeout_ms: int = 30_000


class EngineConfig(BaseModel):
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    cursor: CursorConfig = Field(default_factory=CursorConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
engine/telemetry.py
import logging
import time
from dataclasses import dataclass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


@dataclass
class ActionEvent:
    action: str
    started: float
    finished: float
    success: bool
    error: str | None = None

    @property
    def duration(self):
        return self.finished - self.started


class Telemetry:

    def __init__(self):
        self.events: list[ActionEvent] = []

    def record(
        self,
        action: str,
        started: float,
        success: bool,
        error=None
    ):
        event = ActionEvent(
            action=action,
            started=started,
            finished=time.time(),
            success=success,
            error=error
        )

        self.events.append(event)

        if success:
            logging.info(
                "%s completed in %.3fs",
                action,
                event.duration
            )
        else:
            logging.error(
                "%s failed: %s",
                action,
                error
            )
engine/safety.py
import time
from pathlib import Path

import pyautogui


class SafetyController:

    def __init__(self, config, telemetry):
        self.config = config
        self.telemetry = telemetry
        self.action_count = 0

        if config.fail_safe:
            pyautogui.FAILSAFE = True

        self.screenshot_dir = Path("screenshots")
        self.screenshot_dir.mkdir(exist_ok=True)

    def check(self):

        self.action_count += 1

        if self.action_count > self.config.max_actions:
            raise RuntimeError(
                "Maximum automation action count exceeded"
            )

        time.sleep(self.config.action_delay)

    def emergency_stop(self):
        pyautogui.PAUSE = 0
        raise RuntimeError("Automation emergency stop")

    def capture_error(self):

        filename = (
            self.screenshot_dir /
            f"failure_{int(time.time())}.png"
        )

        pyautogui.screenshot(str(filename))

        return filename
engine/cursor.py
import time

import pyautogui


class CursorController:

    def __init__(self, config, safety, telemetry):
        self.config = config
        self.safety = safety
        self.telemetry = telemetry

    def position(self):
        return pyautogui.position()

    def move_to(self, x: int, y: int):

        started = time.time()

        try:

            self.safety.check()

            pyautogui.moveTo(
                x,
                y,
                duration=self.config.move_duration
            )

            self.telemetry.record(
                "move_cursor",
                started,
                True
            )

        except Exception as exc:

            self.telemetry.record(
                "move_cursor",
                started,
                False,
                str(exc)
            )

            raise

    def click(
        self,
        x=None,
        y=None,
        button="left",
        clicks=1
    ):

        started = time.time()

        try:

            self.safety.check()

            if x is not None and y is not None:
                self.move_to(x, y)

            pyautogui.click(
                clicks=clicks,
                button=button
            )

            self.telemetry.record(
                "click",
                started,
                True
            )

        except Exception as exc:

            self.telemetry.record(
                "click",
                started,
                False,
                str(exc)
            )

            raise

    def double_click(self, x, y):

        self.click(
            x,
            y,
            clicks=2
        )

    def right_click(self, x, y):

        self.click(
            x,
            y,
            button="right"
        )
engine/keyboard.py
import time

import pyautogui


class KeyboardController:

    def __init__(self, safety, telemetry):
        self.safety = safety
        self.telemetry = telemetry

    def type_text(self, text: str):

        started = time.time()

        try:

            self.safety.check()

            pyautogui.write(
                text,
                interval=0.01
            )

            self.telemetry.record(
                "type_text",
                started,
                True
            )

        except Exception as exc:

            self.telemetry.record(
                "type_text",
                started,
                False,
                str(exc)
            )

            raise

    def press(self, key: str):

        self.safety.check()
        pyautogui.press(key)

    def hotkey(self, *keys):

        self.safety.check()
        pyautogui.hotkey(*keys)

    def copy(self):

        self.hotkey("ctrl", "c")

    def paste(self):

        self.hotkey("ctrl", "v")
engine/browser.py
from playwright.async_api import async_playwright


class BrowserController:

    def __init__(self, config):
        self.config = config
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):

        self.playwright = await async_playwright().start()

        self.browser = await self.playwright.chromium.launch(
            headless=self.config.headless
        )

        self.context = await self.browser.new_context()

        self.page = await self.context.new_page()

        self.page.set_default_timeout(
            self.config.timeout_ms
        )

    async def goto(self, url):

        await self.page.goto(
            url,
            wait_until="domcontentloaded"
        )

    async def click(self, selector):

        await self.page.locator(selector).click()

    async def fill(self, selector, value):

        await self.page.locator(selector).fill(value)

    async def text(self, selector):

        return await self.page.locator(
            selector
        ).inner_text()

    async def screenshot(self, path):

        await self.page.screenshot(
            path=path,
            full_page=True
        )

    async def close(self):

        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()
Workflow engine

This is the important part for the actual company.

engine/workflow.py
from dataclasses import dataclass, field
from typing import Callable, Any
import time


@dataclass
class Action:
    name: str
    function: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    retries: int = 0


class Workflow:

    def __init__(self, name: str):
        self.name = name
        self.actions: list[Action] = []

    def add(
        self,
        name: str,
        function: Callable,
        *args,
        retries=0,
        **kwargs
    ):

        self.actions.append(
            Action(
                name=name,
                function=function,
                args=args,
                kwargs=kwargs,
                retries=retries
            )
        )

        return self

    def execute(self):

        results = []

        for action in self.actions:

            attempts = 0

            while True:

                try:

                    result = action.function(
                        *action.args,
                        **action.kwargs
                    )

                    results.append({
                        "action": action.name,
                        "success": True,
                        "result": result
                    })

                    break

                except Exception as exc:

                    attempts += 1

                    if attempts > action.retries:
                        raise RuntimeError(
                            f"Workflow action failed: "
                            f"{action.name}"
                        ) from exc

                    time.sleep(
                        min(2 ** attempts, 10)
                    )

        return results
Visual automation

A cursor automation company eventually needs computer vision rather than relying exclusively on hard-coded coordinates.

engine/vision.py
from pathlib import Path

import cv2


class VisionEngine:

    def __init__(self):
        self.templates = {}

    def load_template(
        self,
        name: str,
        path: str
    ):

        image = cv2.imread(
            str(Path(path)),
            cv2.IMREAD_COLOR
        )

        if image is None:
            raise FileNotFoundError(path)

        self.templates[name] = image

    def locate(
        self,
        screenshot_path: str,
        template_name: str,
        threshold: float = 0.85
    ):

        screen = cv2.imread(
            screenshot_path,
            cv2.IMREAD_COLOR
        )

        template = self.templates[
            template_name
        ]

        result = cv2.matchTemplate(
            screen,
            template,
            cv2.TM_CCOEFF_NORMED
        )

        _, max_value, _, max_location = \
            cv2.minMaxLoc(result)

        if max_value < threshold:
            return None

        height, width = template.shape[:2]

        x = max_location[0] + width // 2
        y = max_location[1] + height // 2

        return {
            "x": x,
            "y": y,
            "confidence": float(max_value)
        }
Main orchestration engine
engine/core.py
from .config import EngineConfig
from .cursor import CursorController
from .keyboard import KeyboardController
from .safety import SafetyController
from .telemetry import Telemetry
from .vision import VisionEngine


class AutomationEngine:

    def __init__(
        self,
        config: EngineConfig | None = None
    ):

        self.config = (
            config or EngineConfig()
        )

        self.telemetry = Telemetry()

        self.safety = SafetyController(
            self.config.safety,
            self.telemetry
        )

        self.cursor = CursorController(
            self.config.cursor,
            self.safety,
            self.telemetry
        )

        self.keyboard = KeyboardController(
            self.safety,
            self.telemetry
        )

        self.vision = VisionEngine()

    def click(self, x, y):

        self.cursor.click(x, y)

    def type(self, text):

        self.keyboard.type_text(text)

    def press(self, key):

        self.keyboard.press(key)

    def screenshot(self, filename):

        import pyautogui

        pyautogui.screenshot(filename)

    def locate_and_click(
        self,
        screenshot,
        template
    ):

        result = self.vision.locate(
            screenshot,
            template
        )

        if result is None:
            raise RuntimeError(
                f"Could not locate {template}"
            )

        self.cursor.click(
            result["x"],
            result["y"]
        )

        return result
Example automation
main.py
from engine.core import AutomationEngine


def main():

    engine = AutomationEngine()

    print(
        "Cursor Automation Engine started."
    )

    print(
        "Current cursor:",
        engine.cursor.position()
    )

    # Example desktop workflow.
    #
    # Replace these coordinates with
    # coordinates from the target application.

    engine.cursor.move_to(
        500,
        400
    )

    engine.cursor.click()

    engine.keyboard.type_text(
        "Cursor Automation"
    )

    engine.keyboard.press(
        "enter"
    )

    print(
        "Workflow completed."
    )


if __name__ == "__main__":
    main()
