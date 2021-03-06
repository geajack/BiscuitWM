# requires python-xlib

import os
import sys
import re
import json
import subprocess
from threading import Timer
import Xlib.threaded
from Xlib import X, display, XK, Xatom, Xcursorfont, error
from Xlib.ext import shape
from x11util import load_font
from ewmh import EWMH

# GLOBAL VARIABLES

FONT_OPTIONS = {
    1: '-adobe-helvetica-bold-r-normal--*-120-*-*-*-*-iso8859-*',
    2: '5x7',
    3: '6x10',
    4: '7x13',
    5: '9x15',
    6: '10x20',
    7: '-misc-fixed-medium-r-normal--8-80-75-75-c-50-iso10646-1',
    8: '-misc-fixed-medium-r-semicondensed--13-120-75-75-c-60-iso10646-1',
    9: '-misc-fixed-medium-r-normal--14-130-75-75-c-70-iso10646-1',
    10: '-misc-fixed-medium-r-normal--13-120-75-75-c-80-iso10646-1',
    11: '-misc-fixed-medium-r-normal--18-120-100-100-c-90-iso10646-1',
    12: '-misc-fixed-medium-r-normal--20-200-75-75-c-100-iso10646-1',
    13: '8x13',
    14: '6x13'
}
FONT_NAME = FONT_OPTIONS[5]
CONFIG_FILE_PATH = "/etc/biscuitwm/biscuitwm.json"


def run_command(command_string):
    try:
        subprocess.Popen(command_string)
    except:
        print("Unable to perform command")


class SessionInfo(object):
    def __init__(self):
        self.session_name = "BiscuitWM"
        self.kernel_version = os.popen('uname -rm').read()[:-1]


class PixelPalette(object):
    def __init__(self, colormap):
        self.colormap = colormap
        self.hex_map = {
            "red": "#ff0000",
            "sienna": "#a0522d",
            "tan": "#d2b48c",
            "green": "#00ff00",
            "blue": "#0000ff",
            "white": "#ffffff",
            "gainsboro": "#dcdcdc",
            "lightgray": "#d3d3d3",
            "darkgray": "#a9a9a9",
            "gray": "#808080",
            "dimgray": "#696969",
            "lightslategray": "#778899",
            "slategray": "#708090",
            "darkslategray": "#2F4F4F",
            "black": "#000000"
        }

    def is_color_hex(self, value):
        match = re.search(r'^#(?:[0-9a-fA-F]{3}){1,2}$', value)
        if match is True:
            return True
        return False

    def get_named_pixel(self, color_name):
        if color_name in self.hex_map.keys():
            return self.colormap.alloc_named_color(self.hex_map[color_name]).pixel
        else:
            return self.colormap.alloc_named_color(self.hex_map["white"]).pixel

    def get_hex_pixel(self, hex_name):
        try:
            return self.colormap.alloc_named_color(hex_name).pixel
        except:
            return self.colormap.alloc_named_color(self.hex_map["white"]).pixel


'''
Thanks to MestreLion for their RepeatedTimer implementation
https://stackoverflow.com/a/13151299
- Standard library only, no external dependencies
- start() and stop() are safe to call multiple times even if the timer has already started/stopped
- function to be called can have positional and named arguments
- You can change interval anytime, it will be effective after next run. Same for args, kwargs and even function!
'''


class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False


class DeskbarItem(object):
    def __init__(self, name, text="", width=0, interval=None, function=None, enabled=True):
        self.name = name
        self.text = text
        self.width = width
        self.interval = interval
        self.function = function
        self.enabled = enabled
        if interval is not None and function is not None:
            self.rt_event = RepeatedTimer(interval, function)
        else:
            self.rt_event = None

    def set_rt_event(self, interval, function):
        self.interval = interval
        self.function = function
        self.rt_event = RepeatedTimer(interval, function)

    def unset_rt_event(self):
        if self.rt_event is not None:
            self.rt_event.stop()
            self.rt_event = None
            self.interval = None
            self.function = None

    def start(self):
        if self.rt_event is not None:
            self.rt_event.start()

    def stop(self):
        if self.rt_event is not None:
            self.rt_event.stop()


class Deskbar(object):
    def __init__(
            self, ewmh, dpy, dpy_root, screen, display_dimensions,
            wm_window_type, wm_window_types, wm_state, wm_window_status,
            prefs, session_info
    ):
        self.ewmh = ewmh
        self.dpy = dpy
        self.dpy_root = dpy_root
        self.screen = screen
        self.colormap = self.screen.default_colormap
        self.pixel_palette = PixelPalette(self.colormap)
        self.system_font = load_font(self.dpy, FONT_NAME)
        self.display_dimensions = display_dimensions

        self.wm_window_type = wm_window_type
        self.wm_window_types = wm_window_types
        self.wm_state = wm_state
        self.wm_window_status = wm_window_status

        self.prefs = prefs
        self.session_info = session_info
        self.time_command = self.set_get_current_time_command()

        self.border_width = 1
        self.height = 20
        self.real_height = self.height + self.border_width

        self.text_y_alignment = 15
        self.padding_leading = 15
        self.padding_between = 20
        self.padding_trailing = 15
        self.color_scheme = self.get_deskbar_color_scheme()

        self.command_string = ""

        self.deskbar = None
        self.deskbar_gc = None

        self.deskbar_items = {
            "leading": {
                "active_window_title": DeskbarItem(
                    "Window Title",
                    text=self.session_info.session_name
                ),
                "window_count": DeskbarItem(
                    "Window Count",
                    text="0 windows",
                    enabled=False
                ),
                "launcher": DeskbarItem(
                    "Launcher",
                    text=self.command_string,
                    enabled=False
                )
            },
            "trailing": {
                "memory_usage": DeskbarItem(
                    "Memory Usage",
                    interval=10,
                    function=self.set_memory_usage
                ),
                "timestamp": DeskbarItem(
                    "Clock",
                    interval=1 if self.prefs.deskbar["clock"]["show_seconds"] == 1 else 30,
                    function=self.set_timestamp,
                    enabled=self.prefs.deskbar["clock"]["enabled"] == 1
                ),
            },
        }

        # Leading items drawn from left to right
        # Trailing items drawn from right to left
        self.deskbar_items_order = {
            "leading": ["window_count", "active_window_title", "launcher"],
            "trailing": ["timestamp", "memory_usage"]
        }

        self.deskbar_update_rt = RepeatedTimer(1, self.update)

    def launcher_is_running(self):
        return self.deskbar_items["leading"]["launcher"].enabled

    def toggle_launcher(self, state=False):
        print("Deskbar launcher mode: " + str(state))
        self.deskbar_items["leading"]["launcher"].enabled = state
        self.command_string = ""
        self.update()

    def set_active_window_title(self, window_title):
        if window_title is None or len(window_title) == 0:
            window_title = self.session_info.session_name
        self.deskbar_items["leading"]["active_window_title"].text = window_title
        self.deskbar_items["leading"]["active_window_title"].width = self.get_string_physical_width(window_title)

    def set_window_count(self, window_count):
        suffix = " windows"
        if window_count == 1:
            suffix = " window"
        window_count_string = str(window_count) + suffix
        self.deskbar_items["leading"]["window_count"].text = window_count_string
        self.deskbar_items["leading"]["active_window_title"].width = self.get_string_physical_width(window_count_string)

    def set_memory_usage(self):
        self.deskbar_items["trailing"]["memory_usage"].text = "MEM: " + self.get_memory_usage() + "%"
        self.deskbar_items["trailing"]["memory_usage"].width = self.get_string_physical_width(
            self.deskbar_items["trailing"]["memory_usage"].text)

    def set_timestamp(self):
        self.deskbar_items["trailing"]["timestamp"].text = self.get_current_time()
        self.deskbar_items["trailing"]["timestamp"].width = self.get_string_physical_width(
            self.deskbar_items["trailing"]["timestamp"].text
        )

    def set_get_current_time_command(self):
        command = 'date +"'
        if self.prefs.deskbar["clock"]["show_day"] == 1:
            command += '%a '
        if self.prefs.deskbar["clock"]["show_date"] == 1:
            command += '%d %b '
        command += '%I:%M'
        if self.prefs.deskbar["clock"]["show_seconds"] == 1:
            command += ':%S'
        command += ' %P"'
        return command

    def get_string_physical_width(self, text):
        font = self.dpy.open_font(FONT_NAME)
        result = font.query_text_extents(text.encode())
        return result.overall_width

    def get_memory_usage(self):
        return os.popen("free -m | awk 'NR==2{printf $3*100/$2}' | xargs printf '%.2f'").read()[:-1]

    def get_current_time(self):
        return os.popen(self.time_command).read()[:-1]

    def start_repeated_events(self):
        for item in self.deskbar_items["leading"].values():
            item.start()
        for item in self.deskbar_items["trailing"].values():
            item.start()
        self.deskbar_update_rt.start()

    def stop_repeated_events(self):
        for item in self.deskbar_items["leading"].values():
            item.stop()
        for item in self.deskbar_items["trailing"].values():
            item.stop()
        self.deskbar_update_rt.stop()

    def get_deskbar_color_scheme(self):
        background_pixel = self.pixel_palette.get_named_pixel("white")
        foreground_pixel = self.pixel_palette.get_named_pixel("black")
        if self.prefs.deskbar["foreground_color"] in self.pixel_palette.hex_map.keys():
            foreground_pixel = self.pixel_palette.get_named_pixel(self.prefs.deskbar["foreground_color"])
        elif self.pixel_palette.is_color_hex(self.prefs.deskbar["foreground_color"]) is True:
            foreground_pixel = self.pixel_palette.get_hex_pixel(self.prefs.deskbar["foreground_color"])
        if self.prefs.deskbar["background_color"] in self.pixel_palette.hex_map.keys():
            background_pixel = self.pixel_palette.get_named_pixel(self.prefs.deskbar["background_color"])
        elif self.pixel_palette.is_color_hex(self.prefs.deskbar["background_color"]) is True:
            background_pixel = self.pixel_palette.get_hex_pixel(self.prefs.deskbar["background_color"])

        return {
            "bg": background_pixel,
            "fg": foreground_pixel
        }

    def draw(self):
        screen_width, screen_height = self.display_dimensions.width, self.display_dimensions.height
        background_pixel, foreground_pixel = self.color_scheme["bg"], self.color_scheme["fg"]

        self.deskbar = self.dpy_root.create_window(
            -self.border_width, -self.border_width, screen_width, self.height, self.border_width,
            self.screen.root_depth,
            background_pixel=background_pixel,
            event_mask=X.StructureNotifyMask | X.ExposureMask | X.ButtonPressMask | X.ButtonReleaseMask,
        )
        self.deskbar_gc = self.deskbar.create_gc(
            font=self.system_font,
            foreground=foreground_pixel,
            background=background_pixel,
        )

        self.deskbar.change_property(
            self.wm_window_type,
            Xatom.ATOM,
            32,
            [self.wm_window_types["dock"]],
            X.PropModeReplace
        )
        self.ewmh.setWmState(self.deskbar, 1, "_NET_WM_DESKTOP")
        self.ewmh.setWmState(self.deskbar, 1, "_NET_WM_STATE_SKIP_TASKBAR")
        self.ewmh.setWmState(self.deskbar, 1, "_NET_WM_STATE_ABOVE")

        self.deskbar.map()  # Draw deskbar
        self.set_timestamp()  # Set initial timestamp
        self.set_memory_usage()  # Set initial memory usage percentage
        self.update()  # Initial update
        self.start_repeated_events()  # Start deskbar updates

    def update(self):
        self.deskbar.clear_area()

        # Leading items
        if self.deskbar_items["leading"]["launcher"].enabled is False:
            for item_key in self.deskbar_items_order["leading"]:
                item = self.deskbar_items["leading"][item_key]
                if item.enabled is True:
                    self.deskbar.draw_text(
                        self.deskbar_gc,
                        self.padding_leading,
                        self.text_y_alignment,
                        item.text.encode('utf-8')
                    )
        else:
            # Launcher takes precedence
            self.deskbar.draw_text(
                self.deskbar_gc,
                self.padding_leading,
                self.text_y_alignment,
                (self.command_string + "|").encode('utf-8')
            )

        # Trailing items
        spacing_from_trailing_end = self.padding_trailing
        for item_key in self.deskbar_items_order["trailing"]:
            item = self.deskbar_items["trailing"][item_key]
            if item.enabled is True:
                self.deskbar.draw_text(
                    self.deskbar_gc,
                    self.display_dimensions.width - (item.width + spacing_from_trailing_end),
                    self.text_y_alignment,
                    item.text.encode('utf-8')
                )
                spacing_from_trailing_end += (item.width + self.padding_between)

    def toggle_window_count(self):
        self.deskbar_items["leading"]["window_count"].enabled = not self.deskbar_items["leading"]["window_count"].enabled
        self.deskbar_items["leading"]["active_window_title"].enabled = not self.deskbar_items["leading"]["window_count"].enabled

'''
Thanks to vulkd for creating xround
https://github.com/vulkd/xround
'''
class DisplayCorners(object):
    def __init__(
            self, ewmh, dpy, dpy_root, screen, display_dimensions,
            wm_window_type, wm_window_types, wm_state, wm_window_status
    ):
        self.ewmh = ewmh
        self.dpy = dpy
        self.dpy_root = dpy_root
        self.screen = screen
        self.colormap = self.screen.default_colormap
        self.pixel_palette = PixelPalette(self.colormap)
        self.system_font = load_font(self.dpy, FONT_NAME)
        self.display_dimensions = display_dimensions

        self.wm_window_type = wm_window_type
        self.wm_window_types = wm_window_types
        self.wm_state = wm_state
        self.wm_window_status = wm_window_status

        self.bg_size = 16
        self.corners = ['nw', 'ne', 'se', 'sw']

        self.display_corners = None

        self.has_run = False

    def draw_corner_pixmap(self, window, arc_start, arc_one, arc_two, pos_in_x=0, pos_in_y=0):
        corner_pm = window.create_pixmap(self.bg_size, self.bg_size, 1)
        corner_gc = corner_pm.create_gc(foreground=1, background=1)
        corner_pm.fill_rectangle(corner_gc, 0, 0, self.bg_size, self.bg_size)
        corner_gc.change(foreground=0)
        corner_pm.fill_arc(corner_gc, pos_in_x, pos_in_y, self.bg_size, self.bg_size, arc_start, arc_one * arc_two)
        return corner_pm

    def draw_corner(self, window, arc_start, arc_one, arc_two, pos_x, pos_y, pos_in_x=0, pos_in_y=0):
        corner_pixmap = self.draw_corner_pixmap(window, arc_start, arc_one, arc_two, pos_in_x, pos_in_y)

        if not self.has_run:
            window.shape_mask(shape.SO.Set, shape.SK.Bounding, pos_x, pos_y, corner_pixmap)
            self.has_run = True
        else:
            window.shape_mask(shape.SO.Union, shape.SK.Bounding, pos_x, pos_y, corner_pixmap)
        return

    def draw(self):
        bg_pm = self.dpy_root.create_pixmap(self.bg_size, self.bg_size, self.screen.root_depth)
        bg_gc = self.dpy_root.create_gc(foreground=self.screen.black_pixel, background=self.screen.black_pixel)
        bg_pm.fill_rectangle(bg_gc, 0, 0, self.bg_size, self.bg_size)

        self.display_corners = self.dpy_root.create_window(
            0, 0, self.display_dimensions.width, self.display_dimensions.height, 0,
            self.screen.root_depth,
            background_pixmap=bg_pm,
            event_mask=X.StructureNotifyMask
        )

        sz = self.bg_size // 2
        if "nw" in self.corners:  # Check for the co-ord in corners array (that can be changed by user)
            self.draw_corner(self.display_corners, 11520, -90, 64, -sz, -sz, sz, sz)
        if "ne" in self.corners:
            self.draw_corner(self.display_corners, 0, 90, 64, self.display_dimensions.width - sz, -sz, -sz, sz)
        if "se" in self.corners:
            self.draw_corner(self.display_corners, 0, -90, 64, self.display_dimensions.width - sz,
                             self.display_dimensions.height - sz, -sz, -sz)
        if "sw" in self.corners:
            self.draw_corner(self.display_corners, -5760, -90, 64, -sz, self.display_dimensions.height - sz, sz, -sz)

        self.display_corners.shape_select_input(0)
        self.display_corners.change_property(self.wm_window_type, Xatom.ATOM, 32, [self.wm_window_types["dock"]],
                                             X.PropModeReplace)

        self.ewmh.setWmState(self.display_corners, 1, "_NET_WM_DESKTOP")
        self.ewmh.setWmState(self.display_corners, 1, "_NET_WM_STATE_SKIP_TASKBAR")
        self.ewmh.setWmState(self.display_corners, 1, "_NET_WM_STATE_ABOVE")

        self.display_corners.map()
        self.update()

    def update(self):
        self.display_corners.raise_window()


class Preferences(object):
    def __init__(self):
        self.dev = {
            "debug": 1
        }
        self.placement = {
            "auto_window_placement": 1,
            "auto_window_fit": 1,
            "auto_window_raise": 1,
            "center_window_placement": 1
        }
        self.deskbar = {
            "enabled": 1,
            "background_color": "white",
            "foreground_color": "black",
            "clock": {
                "enabled": 1,
                "show_day": 1,
                "show_date": 1,
                "show_seconds": 1
            }
        }
        self.xround = {
            "enabled": 1
        }
        self.appearance = {
            "window_border_width": 2,
            "active_window_border_color": "sienna",
            "inactive_window_border_color": "black",
            "background_color": "#D2B48C"
        }

        self.categories = ["dev", "placement", "deskbar", "xround", "appearance"]
        self.read_config(ignore=False)

    def read_config(self, ignore=False):
        if ignore is False:
            if os.path.exists(CONFIG_FILE_PATH):
                with open(CONFIG_FILE_PATH, "r") as user_prefs:
                    user_prefs = json.load(user_prefs)
                    user_prefs_keys = [*user_prefs.keys()]
                    if user_prefs_keys.sort() == self.categories.sort():
                        print("Config file has matching keys")
                        self.dev = user_prefs["dev"]
                        self.placement = user_prefs["placement"]
                        self.deskbar = user_prefs["deskbar"]
                        self.xround = user_prefs["xround"]
                        self.appearance = user_prefs["appearance"]
                    else:
                        print("Config file does not having matching keys!")
            else:
                print("Config file not found!")
        else:
            print("Ignoring config file... using defaults")


class WindowManager(object):
    def __init__(self, prefs, session_info):
        self.prefs = prefs
        self.session_info = session_info
        self.ewmh = EWMH()
        self.dpy = display.Display()
        self.screen = self.dpy.screen()
        self.dpy_root = self.screen.root
        self.colormap = self.screen.default_colormap
        self.pixel_palette = PixelPalette(self.colormap)

        self.display_dimensions = self.get_display_geometry()
        self.window_resize_options = [
            "center",
            "maximize",
            "left",
            "right",
            "top",
            "bottom"
        ]

        self.managed_windows = []
        self.exposed_windows = []
        self.last_raised_window = None
        self.active_window_title = self.session_info.session_name
        self.window_order = -1

        self.key_alias = {}

        self.start = None
        self.attr = None

        self.wm_window_type = self.dpy.intern_atom('_NET_WM_WINDOW_TYPE')
        self.wm_state = self.dpy.intern_atom('_NET_WM_STATE')
        self.wm_window_types = {
            "dock": self.dpy.intern_atom('_NET_WM_WINDOW_TYPE_DOCK'),
            "normal": self.dpy.intern_atom('_NET_WM_WINDOW_TYPE_NORMAL'),
            "dialog": self.dpy.intern_atom('_NET_WM_WINDOW_TYPE_DIALOG'),
            "utility": self.dpy.intern_atom('_NET_WM_WINDOW_TYPE_UTILITY'),
            "toolbar": self.dpy.intern_atom('_NET_WM_WINDOW_TYPE_TOOLBAR'),
            "menu": self.dpy.intern_atom('_NET_WM_WINDOW_TYPE_MENU'),
            "splash": self.dpy.intern_atom('_NET_WM_WINDOW_TYPE_SPLASH')
        }
        self.wm_window_status = {
            "active": self.dpy.intern_atom('_NET_ACTIVE_WINDOW'),
            "desktop": self.dpy.intern_atom('_NET_WM_DESKTOP'),
            "above": self.dpy.intern_atom('_NET_WM_STATE_ABOVE'),
            "skip_taskbar": self.dpy.intern_atom('_NET_WM_STATE_SKIP_TASKBAR'),
            "maximize_vertical": self.dpy.intern_atom('_NET_WM_STATE_MAXIMIZED_VERT'),
            "maximize_horizontal": self.dpy.intern_atom('_NET_WM_STATE_MAXIMIZED_HORIZ')
        }

        self.wm_window_cyclical = [
            self.wm_window_types["normal"],
            self.wm_window_types["dialog"],
            self.wm_window_types["utility"],
            self.wm_window_types["toolbar"]
        ]

        self.deskbar = None
        self.display_corners = None

        self.update_active_window_title_rt = RepeatedTimer(interval=1, function=self.update_active_window_title)
        self.update_active_window_title_rt.stop()

        self.set_cursor(self.dpy_root)

    ### QUERY METHODS

    def get_display_geometry(self):
        return self.dpy_root.get_geometry()

    def window_list(self):
        return self.dpy_root.query_tree().children

    def is_managed_window(self, window):
        return window in self.managed_windows

    def is_alive_window(self, window):
        windows = self.dpy_root.query_tree().children
        return window in windows

    def is_dock(self, window):
        result = None
        try:
            result = window.get_full_property(self.wm_window_type, Xatom.ATOM)
        except error.BadWindow or RuntimeError:
            print("Failed to detect if window is dock")
            pass
        if result is not None and result.value[0] == self.wm_window_types["dock"]:
            return True
        return False

    def is_popup_window(self, window):
        result = None
        try:
            result = window.get_full_property(self.wm_window_type, Xatom.ATOM)
        except error.BadWindow or RuntimeError:
            print("Failed to detect if window is dock")
            pass
        if result is not None and (
                result.value[0] == self.wm_window_types["menu"] or result.value[0] == self.wm_window_types["splash"]):
            return True
        return False

    def is_cyclical_window(self, window):
        result = None
        try:
            result = window.get_full_property(self.wm_window_type, Xatom.ATOM)
        except error.BadWindow or RuntimeError:
            print("Failed to detect if window is dock")
            pass
        if result is not None and result.value[0] in self.wm_window_cyclical:
            return True
        return False

    def is_active(self, atom):
        if atom == self.wm_window_status["active"]:
            return True
        return False

    def get_active_window(self):
        window = None
        try:
            window = self.dpy_root.get_full_property(self.wm_window_status["active"], Xatom.ATOM)
        except:
            print("Failed to get active window")
            pass
        return window

    def get_window_class(self, window):
        try:
            cmd, cls = window.get_wm_class()
        except:
            return ''
        if cls is not None:
            return cls
        else:
            return ''

    def get_window_geometry(self, window):
        try:
            return window.get_geometry()
        except:
            return None

    def get_maximum_available_geometry(self):
        window_width = self.display_dimensions.width
        window_height = self.display_dimensions.height
        if self.deskbar is not None:
            window_height -= self.deskbar.real_height
        return window_width, window_height, self.deskbar is not None

    def get_window_attributes(self, window):
        try:
            return window.get_attributes()
        except:
            return None

    def get_window_state(self, window):
        return self.ewmh.getWmState(window, str=True)

    def get_window_shortname(self, window):
        return '0x{:x} [{}]'.format(window.id, self.get_window_class(window))

    def get_window_title(self, window):
        result = None
        try:
            result = window.get_wm_name()
        except:
            pass
        if result is None:
            return self.session_info.session_name
        return result

    def set_active_window_title(self, window=None, custom_title=None):
        window_title = None
        if window is not None:
            window_title = self.get_window_title(window)
            if window_title is None:
                self.active_window_title = self.session_info.session_name
        elif custom_title is not None:
            window_title = custom_title
        else:
            self.active_window_title = window_title
        if self.prefs.deskbar["enabled"] == 1:
            self.deskbar.set_active_window_title(self.active_window_title)

    def update_active_window_title(self):
        if self.last_raised_window is not None:
            self.set_active_window_title(self.last_raised_window)

    def update_window_count(self):
        if self.deskbar is not None:
            self.deskbar.set_window_count(len(self.managed_windows))

    ### WINDOW CONTROLS

    def manage_window(self, window):
        attributes = self.get_window_attributes(window)
        if attributes is None:
            return
        if attributes.override_redirect:
            return
        if self.is_managed_window(window):
            return

        if self.prefs.dev["debug"] == 1:
            print("Found window: %s", self.get_window_shortname(window))
        self.managed_windows.append(window)
        self.exposed_windows.append(window)
        self.window_order = len(self.managed_windows) - 1
        self.update_window_count()

        window.map()
        mask = X.EnterWindowMask | X.LeaveWindowMask
        window.change_attributes(event_mask=mask)

        self.decorate_window(window)

    def unmanage_window(self, window):
        if self.is_managed_window(window):
            if self.prefs.dev["debug"] == 1:
                print("Unmanaging window: %s", self.get_window_shortname(window))
            if window in self.managed_windows:
                self.managed_windows.remove(window)
                self.window_order = len(self.managed_windows) - 1
                self.update_window_count()
            if window in self.exposed_windows:
                self.exposed_windows.remove(window)

    def destroy_window(self, window):
        if self.is_dock(window) is False:
            if self.prefs.dev["debug"] == 1:
                print("Destroy window: %s", self.get_window_shortname(window))
            if self.is_managed_window(window):
                window.destroy()
                self.unmanage_window(window)

    def raise_window(self, window):
        if not self.is_dock(window):
            if not self.is_managed_window(window):
                return
            window.raise_window()
            self.last_raised_window = window
            self.set_active_window_title(window)
            if self.deskbar is not None:
                self.deskbar.update()

    def focus_window(self, window):
        if self.is_dock(window) or not self.is_managed_window(window) or not self.is_alive_window(window):
            return
        window.set_input_focus(X.RevertToParent, 0)
        self.set_focus_window_border(window)

    def cycle_windows(self):
        if len(self.managed_windows) > 0:
            self.window_order += 1
            if self.window_order > len(self.managed_windows) - 1:
                self.window_order = 0
            window = self.managed_windows[self.window_order]
            if self.is_cyclical_window(window) is False:
                if self.window_order >= len(self.managed_windows) - 1:
                    self.window_order = 0
                else:
                    self.window_order += 1
                window = self.managed_windows[self.window_order]
            self.focus_window(window)
            self.raise_window(window)
        else:
            self.window_order = -1

    ### WINDOW DECORATION

    def is_window_maximized(self, window):
        states = self.get_window_state(window)
        print(states)

    def move_window(self, xdiff, ydiff):
        window_dimensions = self.get_window_geometry(self.start.child)
        if self.deskbar is not None and ydiff < 0 and window_dimensions.y <= self.deskbar.real_height:
            y = self.deskbar.real_height
        else:
            y = self.attr.y + (self.start.detail == 1 and ydiff or 0)
        self.start.child.configure(
            x=self.attr.x + (self.start.detail == 1 and xdiff or 0),
            y=y,
            width=max(1, self.attr.width + (self.start.detail == 3 and xdiff or 0)),
            height=max(1, self.attr.height + (self.start.detail == 3 and ydiff or 0))
        )

    def resize_window(self, window, position):
        if self.is_dock(window) is False:
            if self.prefs.dev["debug"] == 1:
                print("Triggered window resize")
            if position in self.window_resize_options:
                window_x, window_y, window_width, window_height = None, None, None, None
                if position == "center":
                    window_dimensions = self.get_window_geometry(window)
                    window_width, window_height = window_dimensions.width, window_dimensions.height
                    window_x = (self.display_dimensions.width - window_width) // 2
                    window_y = (self.display_dimensions.height - window_height) // 2
                elif position == "maximize":
                    window_width, window_height, has_deskbar = self.get_maximum_available_geometry()
                    window_x = -self.prefs.appearance["window_border_width"]
                    window_y = -self.prefs.appearance["window_border_width"] if not has_deskbar else (
                            -self.prefs.appearance["window_border_width"] + self.deskbar.real_height
                    )
                elif position == "left" or position == "right":
                    window_width = self.display_dimensions.width // 2
                    window_height = self.display_dimensions.height + (
                        0 if self.deskbar is None else self.deskbar.height)
                    if position == "left":
                        window_x = -self.prefs.appearance["window_border_width"]
                    elif position == "right":
                        window_x = window_width - self.prefs.appearance["window_border_width"]
                    window_y = -self.prefs.appearance["window_border_width"] if self.deskbar is None else (
                            -self.prefs.appearance[
                                "window_border_width"] + self.deskbar.height + self.deskbar.border_width
                    )
                elif position == "top" or position == "bottom":
                    window_width = self.display_dimensions.width
                    window_height = (self.display_dimensions.height + (
                        0 if self.deskbar is None else self.deskbar.height)) // 2
                    if position == "top":
                        window_y = -self.prefs.appearance["window_border_width"]
                    elif position == "bottom":
                        window_y = window_height + self.prefs.appearance["window_border_width"]
                    window_x = -self.prefs.appearance["window_border_width"]

                if position == "maximize":
                    self.ewmh.setWmState(window, 1, "_NET_WM_STATE_MAXIMIZED_VERT")
                    self.ewmh.setWmState(window, 1, "_NET_WM_STATE_MAXIMIZED_HORIZ")
                else:
                    self.ewmh.setWmState(window, 0, "_NET_WM_STATE_MAXIMIZED_VERT")
                    self.ewmh.setWmState(window, 0, "_NET_WM_STATE_MAXIMIZED_HORIZ")

                window.configure(
                    x=window_x,
                    y=window_y,
                    width=window_width,
                    height=window_height
                )
            else:
                print("Invalid window position: " + position)

    def decorate_window(self, window):
        self.set_cursor(window)
        if self.is_dock(window) is False:
            window_dimensions = self.get_window_geometry(window)
            window_width, window_height = window_dimensions.width, window_dimensions.height
            window_x = 5
            window_y = 25
            if self.prefs.placement["auto_window_placement"] == 1:
                # Move new window out of the way of the deskbar
                if self.prefs.placement["auto_window_fit"] == 1:
                    # Resize window to fit the screen
                    if window_dimensions.width + window_x >= self.display_dimensions.width:
                        window_width -= window_x * 2
                    if window_dimensions.height + window_y >= self.display_dimensions.height:
                        window_height -= window_y * 2
                if self.prefs.placement["center_window_placement"] == 1:
                    window_x = (self.display_dimensions.width - window_width) // 2
                    window_y = (self.display_dimensions.height - window_height) // 2
                window.configure(
                    x=window_x,
                    y=window_y,
                    width=window_width,
                    height=window_height
                )
            self.set_unfocus_window_border(window)

    def set_unfocus_window_border(self, window):
        if not self.is_dock(window):
            border_color = self.pixel_palette.get_named_pixel("lightgray")
            if self.prefs.appearance["inactive_window_border_color"] in self.pixel_palette.hex_map.keys():
                border_color = self.pixel_palette.get_named_pixel(self.prefs.appearance["inactive_window_border_color"])
            elif self.pixel_palette.is_color_hex(self.prefs.appearance["inactive_window_border_color"]) is True:
                border_color = self.pixel_palette.get_hex_pixel(self.prefs.appearance["inactive_window_border_color"])
            window.configure(border_width=self.prefs.appearance["window_border_width"])
            window.change_attributes(None, border_pixel=border_color)

    def set_focus_window_border(self, window):
        if not self.is_dock(window):
            border_color = self.pixel_palette.get_named_pixel("sienna")
            if self.prefs.appearance["active_window_border_color"] in self.pixel_palette.hex_map.keys():
                border_color = self.pixel_palette.get_named_pixel(self.prefs.appearance["active_window_border_color"])
            elif self.pixel_palette.is_color_hex(self.prefs.appearance["active_window_border_color"]) is True:
                border_color = self.pixel_palette.get_hex_pixel(self.prefs.appearance["active_window_border_color"])
            window.change_attributes(None, border_pixel=border_color)

    def set_cursor(self, window):
        font = self.dpy.open_font('cursor')
        cursor = font.create_glyph_cursor(
            font,
            Xcursorfont.left_ptr,
            Xcursorfont.left_ptr + 1,
            (65535, 65535, 65535),
            (0, 0, 0)
        )
        window.change_attributes(cursor=cursor)

    def set_background_color(self):
        background_color = self.pixel_palette.hex_map["slategray"]
        if self.pixel_palette.is_color_hex(self.prefs.appearance["background_color"]) is True:
            background_color = self.prefs.appearance["background_color"]
        elif self.prefs.appearance["background_color"] in self.pixel_palette.hex_map.keys():
            background_color = self.pixel_palette.hex_map[self.prefs.appearance["background_color"]]
        os.system('xsetroot -solid "' + background_color + '"')

    # DEBUG

    def print_event_type(self, ev):
        event = ev.type
        msg = None
        if event == X.CreateNotify:
            msg = "CreateNotify"
        elif event == X.DestroyNotify:
            msg = "DestroyNotify"
        elif event == X.MapNotify:
            msg = "MapNotify"
        elif event == X.FocusIn:
            msg = "FocusIn"
        elif event == X.FocusOut:
            msg = "FocusIn"
        elif event == X.EnterNotify:
            msg = "EnterNotify"
        elif event == X.LeaveNotify:
            msg = "LeaveNotify"
        elif event == X.MotionNotify:
            msg = "MotionNotify"
        elif event == X.KeyPress:
            msg = "KeyPress"
        elif event == X.ButtonPress:
            msg = "ButtonPress"
        else:
            return
        print(msg + " event")

    # SPECIAL

    def start_terminal(self):
        run_command('x-terminal-emulator')

    # EVENT HANDLING

    def keycode_to_string(self, detail):
        return XK.keysym_to_string(self.dpy.keycode_to_keysym(detail, 0))

    def set_key_aliases(self):
        keystrings = [
            "x", "q",
            "minus", "equal", "bracketleft", "bracketright", "backslash", "slash",
            "F1", "Tab", "Escape", "space", "Return", "BackSpace"
        ]
        for keystring in keystrings:
            self.key_alias[keystring] = self.dpy.keysym_to_keycode(XK.string_to_keysym(keystring))

    def handle_launcher(self, ev):
        if ev.detail == self.key_alias["Escape"]:
            self.deskbar.toggle_launcher(state=False)
        elif ev.detail == self.key_alias["BackSpace"] and len(self.deskbar.command_string) > 0:
            self.deskbar.command_string = self.deskbar.command_string[:-1]
            self.deskbar.update()
        elif ev.detail == self.key_alias["Return"]:
            run_command(self.deskbar.command_string)
            self.deskbar.toggle_launcher(state=False)
        else:
            try:
                key_pressed = self.keycode_to_string(ev.detail)
                if key_pressed is not None:
                    self.deskbar.command_string += key_pressed
                    self.deskbar.update()
            except:
                print("Invalid key press detection")

    def handle_keypress(self, ev):
        if ev.detail in self.key_alias.values():
            print("Key is aliased")
            if ev.detail == self.key_alias["x"]:
                self.start_terminal()
            elif ev.detail == self.key_alias["q"] and ev.child != X.NONE:
                self.destroy_window(ev.child)
            elif ev.detail == self.key_alias["minus"] and ev.child != X.NONE:
                self.resize_window(ev.child, "center")
            elif ev.detail == self.key_alias["equal"] and ev.child != X.NONE:
                self.resize_window(ev.child, "maximize")
            elif ev.detail == self.key_alias["bracketleft"] and ev.child != X.NONE:
                self.resize_window(ev.child, "left")
            elif ev.detail == self.key_alias["bracketright"] and ev.child != X.NONE:
                self.resize_window(ev.child, "right")
            elif ev.detail == self.key_alias["backslash"] and ev.child != X.NONE:
                self.resize_window(ev.child, "top")
            elif ev.detail == self.key_alias["slash"] and ev.child != X.NONE:
                self.resize_window(ev.child, "bottom")
            elif ev.detail == self.key_alias["F1"] and ev.child != X.NONE:
                self.focus_window(ev.window)
                self.raise_window(ev.window)
            elif ev.detail == self.key_alias["Tab"]:
                self.cycle_windows()
            elif ev.detail == self.key_alias["space"]:
                if self.deskbar is not None:
                    self.deskbar.toggle_launcher(state=True)
            elif ev.detail == self.key_alias["Escape"]:
                self.end_session()
        else:
            print("Key is not aliased")

    def loop(self):
        while 1:
            ev = self.dpy.next_event()
            if self.prefs.dev["debug"] == 1:
                self.print_event_type(ev)

            if ev.type in [X.EnterNotify, X.LeaveNotify, X.MapNotify]:
                self.set_active_window_title(ev.window)

            if ev.type == X.KeyPress:
                if self.deskbar is not None and self.deskbar.launcher_is_running() is True:
                    self.handle_launcher(ev)
                else:
                    self.handle_keypress(ev)
            elif ev.type == X.MapNotify:
                if self.is_cyclical_window(ev.window):
                    try:
                        self.manage_window(ev.window)
                        self.focus_window(ev.window)
                        self.raise_window(ev.window)
                    except AttributeError:
                        print("Unable to handle new window")
                        pass
            elif ev.type == X.DestroyNotify:
                try:
                    self.destroy_window(ev.window)
                except AttributeError:
                    print("Unable to unhandle new window")
                    pass
            elif ev.type == X.EnterNotify:
                self.focus_window(ev.window)
                if self.prefs.placement["auto_window_raise"] == 1:
                    self.raise_window(ev.window)
            elif ev.type == X.LeaveNotify:
                self.set_unfocus_window_border(ev.window)
            elif ev.type == X.ButtonPress and ev.child != X.NONE:
                if not self.is_dock(ev.child):
                    self.raise_window(ev.child)
                    self.set_focus_window_border(ev.child)
                    self.attr = ev.child.get_geometry()
                    self.start = ev
                elif self.deskbar is not None and ev.child == self.deskbar.deskbar:
                    if ev.detail == 1:
                        self.cycle_windows()
                    elif ev.detail == 3:
                        self.deskbar.toggle_window_count()
                        self.deskbar.update()
            elif ev.type == X.MotionNotify and self.start:
                xdiff = ev.root_x - self.start.root_x
                ydiff = ev.root_y - self.start.root_y
                self.move_window(xdiff, ydiff)
            elif ev.type == X.ButtonRelease:
                self.start = None
                self.attr = None
                if ev.child != X.NONE and self.is_dock(ev.child) is False:
                    self.ewmh.setWmState(ev.window, 0, "_NET_WM_STATE_MAXIMIZED_VERT")
                    self.ewmh.setWmState(ev.window, 0, "_NET_WM_STATE_MAXIMIZED_HORIZ")

            if self.display_corners is not None:
                self.display_corners.update()
            self.dpy.flush()

    def main(self):
        # Register keyboard and mouse events
        self.set_key_aliases()
        self.dpy_root.grab_key(
            X.AnyKey,
            X.Mod1Mask | X.Mod2Mask,
            1,
            X.GrabModeAsync,
            X.GrabModeAsync
        )
        self.dpy_root.grab_button(
            1,
            X.Mod1Mask | X.Mod2Mask,
            1,
            X.ButtonPressMask | X.ButtonReleaseMask | X.PointerMotionMask,
            X.GrabModeAsync,
            X.GrabModeAsync,
            X.NONE,
            X.NONE
        )
        self.dpy_root.grab_button(
            3,
            X.Mod1Mask | X.Mod2Mask,
            1,
            X.ButtonPressMask | X.ButtonReleaseMask | X.PointerMotionMask,
            X.GrabModeAsync,
            X.GrabModeAsync,
            X.NONE,
            X.NONE
        )
        self.dpy_root.change_attributes(event_mask=X.SubstructureNotifyMask)

        self.set_background_color()

        children = self.window_list()
        for child in children:
            if child.get_attributes().map_state:
                self.manage_window(child)

        # Draw deskbar
        if self.prefs.deskbar["enabled"] == 1:
            self.deskbar = Deskbar(
                self.ewmh, self.dpy, self.dpy_root, self.screen, self.display_dimensions,
                self.wm_window_type, self.wm_window_types,
                self.wm_state, self.wm_window_status,
                self.prefs, self.session_info
            )
            self.deskbar.draw()

        # Draw display corners
        if self.prefs.xround["enabled"] == 1:
            self.display_corners = DisplayCorners(
                self.ewmh, self.dpy, self.dpy_root, self.screen, self.display_dimensions,
                self.wm_window_type, self.wm_window_types,
                self.wm_state, self.wm_window_status
            )
            self.display_corners.draw()

        try:
            self.loop()
        except KeyboardInterrupt or error.ConnectionClosedError:
            self.end_session()
            sys.exit(0)

    def end_session(self):
        self.update_active_window_title_rt.stop()
        if self.prefs.deskbar["enabled"] == 1:
            self.deskbar.stop_repeated_events()
        if self.prefs.xround["enabled"] == 1:
            self.display_corners.stop()
        self.dpy.close()
        sys.exit(0)


if __name__ == "__main__":
    WindowManager(prefs=Preferences(), session_info=SessionInfo()).main()
