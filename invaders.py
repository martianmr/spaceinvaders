"""
Space Invaders — an authentic recreation of the 1978 Taito arcade classic.

Controls
--------
Left/Right arrows or A/D  : move the cannon
Space/LCtrl               : fire
P                         : pause
Enter/Space               : start
Esc                       : quit
F                         : fullscreen

The game faithfully reproduces the core mechanics of the original:
  * A 5 x 11 formation of three invader types (squid = 30, crab = 20,
    octopus = 10 points) that marches side to side, drops a row at each
    screen edge, and speeds up as its numbers are thinned out.
  * A single player cannon that can fire only one shot at a time.
  * Four destructible bunkers that are eroded by player and invader shots.
  * A mystery UFO that periodically crosses the top of the screen for a
    pseudorandom bonus (50 / 100 / 150 / 300 points).
  * Three lives, a persistent high score, and a four-note bass
    heartbeat that accelerates as the invaders are destroyed.
"""

import array
import math
import os
import random
import sys

import pygame
from enum import Enum

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

DEBUG = False               # When set to True shows left/right scan border and info on player shots
SHOWPAUSE = True            # Disable to hide pause message

FPS = 59.541985             # Refresh speed in Hz

BLACK = (0, 0, 0)
GREEN = (0, 255, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)

HIGH_SCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "highscore.txt")
EXTRA_LIFE_SCORE = 1500

UFO_TIME = 1536             # Frames before UFO appears after initial top row drop or new wave
PLAYER_WAIT = 129           # Frames before enabling player
ENEMY_FIRE_WAIT = 175       # Frames before invaders start firing at start of wave or after player death
TITLE_TIME = 900            # Frames for each title screen

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

SCALE = 3          # number of screen pixels to each sprite pixel

SCREEN_WIDTH = 224 * SCALE  # Original space invaders is 224*256 (X*Y) 
SCREEN_HEIGHT = 224 * SCALE # We reduce the Y axis a bit to better fit a landscape monitor

INVADER_COLS = 11
INVADER_ROWS = 5
INVADER_SPACING = 16 * SCALE
INVADER_DROP = 8 * SCALE

INVADER_TOP = SCREEN_HEIGHT - 176 * SCALE
INVADER_LEFT = 8 * SCALE
INVADER_RIGHT = SCREEN_WIDTH - 10 * SCALE
UFO_Y = INVADER_TOP - 24 * SCALE
PLAYER_Y = SCREEN_HEIGHT - 16 * SCALE
PLAYER_LEFT = 18 * SCALE
PLAYER_RIGHT = SCREEN_WIDTH - 24 * SCALE
BUNKER_Y = SCREEN_HEIGHT - 48 * SCALE

# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

SAMPLE_RATE = 22050
_sound_ok = False


def _make_square(ms, vol=0.5, freq=440.0):
    """A raw square wave"""
    n = int(SAMPLE_RATE * ms / 1000.0)
    buf = array.array("h")
    # rng = random.Random()
    for i in range(n):
        t = i / SAMPLE_RATE
        val = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        buf.append(int(val * vol * 32767))
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _make_noise(ms, vol=0.5):
    """White noise, used for explosions."""
    n = int(SAMPLE_RATE * ms / 1000.0)
    buf = array.array("h")
    rng = random.Random()
    for i in range(n):
        if (i // 4) % 2 == 0:
            buf.append(int(rng.uniform(-1.0, 1.0) * vol * 32767))
        else:
            buf.append(0)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _make_sweep(ms=120, vol=0.35):
    """A quick descending square-wave sweep for the player's shot."""
    n = int(SAMPLE_RATE * ms / 1000.0)
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        freq = 900.0 - (900.0 - 150.0) * (i / n)
        phase += 2 * math.pi * freq / SAMPLE_RATE
        val = 1.0 if math.sin(phase) >= 0 else -1.0
        buf.append(int(val * vol * 32767))
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _make_ufo(ms=600, vol=0.4):
    """A warbling tone for the mystery UFO."""
    n = int(SAMPLE_RATE * ms / 1000.0)
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = 400.0 + 120.0 * math.sin(2 * math.pi * 6.0 * t)
        phase += 2 * math.pi * freq / SAMPLE_RATE
        buf.append(int(math.sin(phase) * vol * 32767))
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _make_wav(filename, vol=0.5):
    """Load a WAV file and return a pygame.mixer.Sound object."""
    if not os.path.exists(filename):
        return None
    sound = pygame.mixer.Sound(filename)
    sound.set_volume(vol)
    return sound


def _make_sound(filename, vol, fallback_func, ms, freq=None):
    """Load a WAV file if it exists, otherwise generate a sound."""
    return _make_wav(filename, vol) if os.path.exists(filename) else fallback_func(ms, vol, freq) if freq is not None else fallback_func(ms, vol)


def init_audio():
    """Initialise the mixer and build all game sounds."""
    global _sound_ok
    sounds = {}
    try:
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 4, 512)
        pygame.mixer.init()
        _sound_ok = True
    except pygame.error:
        _sound_ok = False
        return sounds

    sounds["bass"] = [_make_sound("sounds/march%d.wav" % i, 0.3, _make_square, 200, f)
                      for f,i in ((13.75, 1), (12.975, 2), (12.25, 3), (11.55, 4))] # four-note bass heartbeat.
    sounds["shoot"] = _make_sound("sounds/playerfire.wav", 0.2, _make_sweep, 120)
    sounds["invader_killed"] = _make_sound("sounds/invaderdie.wav", 0.45, _make_noise, 90)
    sounds["player_death"] = _make_sound("sounds/explosion.wav", 0.55, _make_noise, 500)
    sounds["ufo"] = _make_sound("sounds/ufo.wav", 0.4, _make_ufo, 600)
    sounds["ufo_killed"] = _make_sound("sounds/ufodie.wav", 0.5, _make_noise, 250)
    sounds["extra_life"] = _make_sound("sounds/extralife.wav", 0.6, _make_sweep, 500)
    return sounds


# ---------------------------------------------------------------------------
# Sprite data
# ---------------------------------------------------------------------------

SQUID = (
    "...XX...",
    "..XXXX..",
    ".XXXXXX.",
    "XX.XX.XX",
    "XXXXXXXX",
    "..X..X..",
    ".X.XX.X.",
    "X.X..X.X",
), (
    "...XX...",
    "..XXXX..",
    ".XXXXXX.",
    "XX.XX.XX",
    "XXXXXXXX",
    ".X.XX.X.",
    "X......X",
    ".X....X.",
)

CRAB = (
    "..X.....X..",
    "X..X...X..X",
    "X.XXXXXXX.X",
    "XXX.XXX.XXX",
    "XXXXXXXXXXX",
    ".XXXXXXXXX.",
    "..X.....X..",
    ".X.......X.",
), (
    "..X.....X..",
    "...X...X...",
    "..XXXXXXX..",
    ".XX.XXX.XX.",
    "XXXXXXXXXXX",
    "X.XXXXXXX.X",
    "X.X.....X.X",
    "...XX.XX...",
)

OCTOPUS = (
    "....XXXX....",
    ".XXXXXXXXXX.",
    "XXXXXXXXXXXX",
    "XXX..XX..XXX",
    "XXXXXXXXXXXX",
    "...XX..XX...",
    "..XX.XX.XX..",
    "XX........XX",
), (
    "....XXXX....",
    ".XXXXXXXXXX.",
    "XXXXXXXXXXXX",
    "XXX..XX..XXX",
    "XXXXXXXXXXXX",
    "..XXX..XXX..",
    ".XX..XX..XX.",
    "...XX..XX...",
)

ENEMY_DEAD = (
    "....X...X....",
    ".X...X.X...X.",
    "..X.......X..",
    "...X.....X...",
    "XX.........XX",
    "...X.....X...",
    "..X..X.X..X..",
    ".X..X...X..X.",
)

PLAYER = (
    "......X......",
    ".....XXX.....",
    ".....XXX.....",
    ".XXXXXXXXXXX.",
    "XXXXXXXXXXXXX",
    "XXXXXXXXXXXXX",
    "XXXXXXXXXXXXX",
    "XXXXXXXXXXXXX",
)

PLAYER_DEAD = (
    "......X.........",
    "...........X....",
    "......X.X.X.....",
    "...X..X.........",
    ".......XX.XX....",
    ".X...X.XX.X.X...",
    "...XXXXXXXX..X..",
    "..XXXXXXXXXX.X.X",
), (
    "...X.........X..",
    "X.....X....XX..X",
    "...X....XX......",
    "......X.......X.",
    ".X..X.XX..XX...X",
    "..X....XXX...X..",
    "...XXXXXXXXX....",
    "..XX.XXXXXXX..X.",
)

UFO_SPRITE = (
    ".....XXXXXX.....",
    "...XXXXXXXXXX...",
    "..XXXXXXXXXXXX..",
    ".XX.XX.XX.XX.XX.",
    "XXXXXXXXXXXXXXXX",
    "..XXX..XX..XXX..",
    "...X........X...",
)

UFO_EXPLODE = (
    "..X..X.X......X.X..X.",
    "...X........XX....X..",
    "X.X...XXXX...XX......",
    ".....XXXXXXX..XXX..X.",
    "....XXX.X.X.X..XXX..X",
    "..X...XXXXX...XX.....",
    "X......X.X...XX...X..",
    "..X...X...X....X.....",
)

# The bunker shield: a 22 x 16 block with an arched notch at the bottom.
BUNKER = (
    "....XXXXXXXXXXXXXX....",
    "...XXXXXXXXXXXXXXXX...",
    "..XXXXXXXXXXXXXXXXXX..",
    ".XXXXXXXXXXXXXXXXXXXX.",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXXXXXXXXXXXXXXXXX",
    "XXXXXXX.......XXXXXXXX",
    "XXXXXX.........XXXXXXX",
    "XXXXX...........XXXXXX",
    "XXXXX...........XXXXXX",
)

GROUND = (('X' * (SCREEN_WIDTH // SCALE)),)

PLAYER_SHOT = (
    "X",
    "X",
    "X",
    "X",
),

ENEMY_SHOTS = ((
    ".X.",
    ".X.",
    ".X.",
    ".X.",
    ".X.",
    ".X.",
    ".X.",
), (
    ".X.",
    ".X.",
    "XX.",
    ".XX",
    ".X.",
    "XX.",
    ".XX",
), (
    ".X.",
    ".X.",
    ".X.",
    ".X.",
    ".X.",
    ".X.",
    ".X.",
), (
    ".XX",
    "XX.",
    ".X.",
    ".XX",
    "XX.",
    ".X.",
    ".X.",
)), ((
    ".X.",
    ".X.",
    ".X.",
    ".X.",
    ".X.",
    "XXX",
), (
    ".X.",
    ".X.",
    ".X.",
    "XXX",
    ".X.",
    ".X.",
), (
    ".X.",
    ".X.",
    "XXX",
    ".X.",
    ".X.",
    ".X.",
), (
    "XXX",
    ".X.",
    ".X.",
    ".X.",
    ".X.",
    ".X.",
)), ((
    ".X.",
    "X..",
    ".X.",
    "..X",
    ".X.",
    "X..",
    ".X.",
), (
    "X..",
    ".X.",
    "..X",
    ".X.",
    "X..",
    ".X.",
    "..X",
), (
    ".X.",
    "..X",
    ".X.",
    "X..",
    ".X.",
    "..X",
    ".X.",
), (
    "..X",
    ".X.",
    "X..",
    ".X.",
    "..X",
    ".X.",
    "X..",
))

ENEMY_SHOT_EXPLODE = (
    "..X...",
    "X...X.",
    "..XX.X",
    ".XXXX.",
    "X.XXX.",
    ".XXXXX",
    "X.XXX.",
    ".X.X.X",
)

PLAYER_SHOT_EXPLODE = (
    "X...X..X",
    "..X...X.",
    ".XXXXXX.",
    "XXXXXXXX",
    "XXXXXXXX",
    ".XXXXXX.",
    "..X..X..",
    "X..X...X",
)

UPSIDE_DOWN_Y = (
    ".....",
    "..X..",
    "..X..",
    "..X..",
    "..X..",
    ".X.X.",
    "X...X",
    "X...X",
)

SQUID_PULLING_Y = (
    "..........XX...",
    "....X....XXXX..",
    "....X...XXXXXX.",
    "....XX.XX.XX.XX",
    "....X.XXXXXXXXX",
    "...X.X...X..X..",
    "..X...X.X.XX.X.",
    "..X...XX.X..X.X",
), (
    "..........XX...",
    "...X.....XXXX..",
    "...X....XXXXXX.",
    "...XXX.XX.XX.XX",
    "...X..XXXXXXXXX",
    "..X.X...X.XX.X.",
    ".X...X.X......X",
    ".X...X..X....X.",
)

SQUID_PUSHING_Y = (
    "..........XX...",
    ".X...X...XXXX..",
    ".X...XX.XXXXXX.",
    "..X.X.XXX.XX.XX",
    "...X..XXXXXXXXX",
    "...X.....X..X..",
    "...X....X.XX.X.",
    "...X...X.X..X.X",
), (
    "..........XX...",
    "X...X....XXXX..",
    "X...XX..XXXXXX.",
    ".X.X.XXXX.XX.XX",
    "..X...XXXXXXXXX",
    "..X.....X.XX.X.",
    "..X....X......X",
    "..X.....X....X.",
)


def build_sprite(rows, color, scale=SCALE):
    """Turn a list of 'X'/'.' strings into a scaled pygame.Surface."""
    height = len(rows)
    width = len(rows[0])
    surf = pygame.Surface((width * scale, height * scale), pygame.SRCALPHA)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == "X":
                surf.fill(color, (x * scale, y * scale, scale, scale))
    return surf


# ---------------------------------------------------------------------------
# Game objects
# ---------------------------------------------------------------------------


class Player:
    def __init__(self, image):
        """Setup the player base"""
        self.image = image
        self.rect = image.get_rect()
        self.dead_rect = image.get_rect()
        self.death_anim = 0
        self.rect.bottom = PLAYER_Y
        self.speed = SCALE
        self.active = False
        self.reset()

    def reset(self):
        """Reset the player base position"""
        self.rect.left = PLAYER_LEFT
        self.wait = PLAYER_WAIT

    def update(self, keys):
        """Call this every frame to enable or move the base"""
        if self.wait > 0:
            self.wait -=1
            if self.wait > 0:
                return
        self.active = True
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.rect.x -= self.speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.rect.x += self.speed
        self.rect.clamp_ip(pygame.Rect(PLAYER_LEFT, 0, PLAYER_RIGHT - PLAYER_LEFT, SCREEN_HEIGHT))


class Invader:
    def __init__(self, frames, points, x, y, col, row):
        """Setup a space invader"""
        self.frames = frames
        self.points = points
        self.rect = frames[0].get_rect(topleft=(x, y))
        self.frame = 0
        self.row = row
        self.col = col
        self.dead_timer = 17
        self.dead_scan = ""
        self.enabled = False

    def image(self):
        """Return the current animation frame"""
        return self.frames[self.frame]


# See _update_enemy_fire() for details of shot types
class ShotType(Enum):
    ROLLING = 0
    PLUNGER = 1
    SQUIGGLY = 2


class Shot:
    def __init__(self, frames, explosion, x, y, dy, friendly, type = 0, count = 0):
        """Setup a player or enemy shot"""
        self.frames = frames
        self.rect = frames[0].get_rect()
        self.rect.left = x
        self.rect.top = y
        self.dy = dy
        self.friendly = friendly
        self.move_count = 1
        self.frame = self.move_count % len(self.frames)
        self.count = count
        self.type = type
        self.started = True if self.friendly else False # Delay enemy shots on creation
        self.alive = True
        self.exploding_count = 0
        self.exploding_length = 17 if self.friendly else 4 # How many cycles it takes for the shot explosion to complete
        self.exploding_image = explosion
        self.exploding_rect = explosion.get_rect()
        if self.friendly:
            self.xoff = -3
            self.yoff = -2
        else:
            self.xoff = -2
            self.yoff = 2

    def explode(self, immediate = False):
        """Mark this shot as exploding"""
        if not self.alive:
            return
        self.alive = False
        self.exploding_count = self.exploding_length - 1 if immediate else self.exploding_length
        self.exploding_rect.left = self.rect.left + (SCALE * self.xoff)
        self.exploding_rect.top = self.rect.top + (SCALE * self.yoff)

    def update(self):
        """Call this every frame to enable and move the shot"""
        if not self.started:
            self.started = True
            return
        self.move_count = self.move_count + 1
        if self.alive:
            self.rect.y += self.dy
            self.frame = self.move_count % len(self.frames)
        else:
            self.exploding_count -= 1

    def image(self):
        """Return the current animation frame"""
        return self.frames[self.frame]


class UFO:
    def __init__(self, image):
        """Setup a UFO object"""
        self.image = image
        self.rect = image.get_rect()
        self.rect.y = UFO_Y
        self.speed = 2 * SCALE
        self.active = False
        self.ready = False
        self.direction = 1
        self.dead_timer = 0
        self.bonus = 0

    def spawn(self, direction):
        """Make the UFO active and spawn left or right depending on the player shot count"""
        self.active = True
        self.direction = direction
        if self.direction == 1:
            self.rect.left = INVADER_LEFT
        else:
            self.rect.right = INVADER_RIGHT

    def update(self):
        """Call this every frame to enable and move the UFO"""
        if not self.active:
            return False
        self.rect.x += self.speed * self.direction
        if self.rect.left < INVADER_LEFT or self.rect.right > INVADER_RIGHT:
            self.active = False
            return True
        return False


class Bunker:
    def __init__(self, rows, x, y):
        """Setup a bunker with a sprite and a grid to hold damage"""
        self.rows = rows
        self.grid = [[ch == "X" for ch in row] for row in rows]
        self.width = len(rows[0])
        self.height = len(rows)
        self.rect = pygame.Rect(x, y, self.width * SCALE, self.height * SCALE)
        self.image = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        self._rebuild()

    def _rebuild(self):
        """Update the bunker sprite to reflect current damage in the grid"""
        self.image.fill((0, 0, 0, 0))
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x]:
                    self.image.fill(
                        GREEN,
                        (x * SCALE, y * SCALE, SCALE, SCALE))

    def stomp(self, inv):
        """Erode bunker when alien stomps all over it"""
        changed = False
        left = (inv.rect.left - self.rect.x) // SCALE
        top = (inv.rect.top - self.rect.y) // SCALE
        right = (inv.rect.right - self.rect.x) // SCALE
        bottom = (inv.rect.bottom - self.rect.y) // SCALE
        for y in range(top, bottom):
            for x in range(left, right):
                if 0 <= x < self.width and 0 <= y < self.height:
                    if self.grid[y][x]:
                        self.grid[y][x] = False
                        changed = True
        if changed:
            self._rebuild()

    def damage_from_rows(self, rows, cx, cy, test = False):
        """Erode bunker from a list of rows."""
        changed = False
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch == "X":
                    gx = cx + x
                    gy = cy + y
                    if 0 <= gx < self.width and 0 <= gy < self.height:
                        if self.grid[gy][gx]:
                            if not test:
                                self.grid[gy][gx] = False
                            changed = True
        return changed

    def damage(self, shot, force = False):
        """Erode the bunker from explosion sprite.
        
        First check each pixel in the shot sprite and remove those pixels from the bunker. If we removed anything the shot hit the bunker so
        remove all the shot explosion pixels as well. Return if we changed so the shot knows if it's exploding or not.
        """
        cx = (shot.rect.left - self.rect.x) // SCALE
        cy = (shot.rect.top - self.rect.y) // SCALE
        changed = False
        if shot.friendly:
            changed = self.damage_from_rows(PLAYER_SHOT[0], cx, cy, test = True)
            if changed:
                self.damage_from_rows(PLAYER_SHOT_EXPLODE, cx + shot.xoff, cy + shot.yoff)
        else:
            changed = self.damage_from_rows(ENEMY_SHOTS[shot.type][shot.frame], cx, cy)
            if changed or force:
                self.damage_from_rows(ENEMY_SHOT_EXPLODE, cx + shot.xoff, cy + shot.yoff)
        if changed or force:
            self._rebuild()
        return changed

# ---------------------------------------------------------------------------
# Main Game class
# ---------------------------------------------------------------------------


class Game:
    def __init__(self):
        """Initialise the main game object"""
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
        pygame.mouse.set_visible(False)
        pygame.display.set_caption("Space Invaders")
        try:
            icon = pygame.image.load('images/icon.png')
            pygame.display.set_icon(icon)
        except OSError:
            pass
        self.clock = pygame.time.Clock()
        self.sounds = init_audio()
        self.mute = True
        
        # Attempt to load spaceinvaders font
        space_invaders_font = "fonts/space_invaders.ttf" if os.path.exists("fonts/space_invaders.ttf") else None
        font_size = [16, 24, 72] if space_invaders_font is not None else [24, 40, 96]
        self.font_small = pygame.font.Font(space_invaders_font, font_size[0])
        self.font_medium = pygame.font.Font(space_invaders_font, font_size[1])
        self.font_large = pygame.font.Font(space_invaders_font, font_size[2])

        # Pre-render sprites.
        self.squid = [build_sprite(f, WHITE) for f in SQUID]
        self.crab = [build_sprite(f, WHITE) for f in CRAB]
        self.octopus = [build_sprite(f, WHITE) for f in OCTOPUS]
        self.enemy_dead = build_sprite(ENEMY_DEAD, WHITE)
        self.player_img = build_sprite(PLAYER, GREEN)
        self.player_dead_img = [build_sprite(f, GREEN) for f in PLAYER_DEAD]
        self.player_shot = [build_sprite(f, WHITE) for f in PLAYER_SHOT]
        self.player_shot_explode = build_sprite(PLAYER_SHOT_EXPLODE, WHITE)
        self.ufo_img = build_sprite(UFO_SPRITE, RED)
        self.ufo_dead = build_sprite(UFO_EXPLODE, RED)
        self.enemy_shot = [[build_sprite(f, WHITE) for f in i] for i in ENEMY_SHOTS]
        self.enemy_shot_explode = build_sprite(ENEMY_SHOT_EXPLODE, WHITE)
        self.ufo_icon = build_sprite(UFO_SPRITE, RED, scale=2)
        self.squid_icon = build_sprite(SQUID[0], GREEN, scale=2)
        self.crab_icon = build_sprite(CRAB[0], GREEN, scale=2)
        self.octopus_icon = build_sprite(OCTOPUS[0], GREEN, scale=2)
        self.upside_down_y = build_sprite(UPSIDE_DOWN_Y, WHITE)
        self.squid_pulling_y = [build_sprite(f, WHITE) for f in SQUID_PULLING_Y]
        self.squid_pushing_y = [build_sprite(f, WHITE) for f in SQUID_PUSHING_Y]

        # Initial values for the high score table
        self.high_score_table = self._load_high_score()
        self.high_score = self.high_score_table[0]["score"]
        self.high_score_name = ""

        self.state = "title"  # Show the title screen on start
        self.title_variant = False
        self.laststate = self.state
        self.reload_times = {300: 48, 1100: 16, 3100: 8, -1: 7}   # How fast the invaders fire increases with score
        self.shot_column = {
            ShotType.PLUNGER.value : [0x01, 0x07, 0x01, 0x01, 0x01, 0x04, 0x0b, 0x01, 0x06, 0x03, 0x01, 0x01, 0x0b, 0x09, 0x02, 0x08],
            ShotType.SQUIGGLY.value : [0x0b, 0x01, 0x06, 0x03, 0x01, 0x01, 0x0b, 0x09, 0x02, 0x08, 0x02, 0x0b, 0x04, 0x07, 0x0a]
        } # List of columns that each type of enemy shot will use in the formation
        self.demo_commands = [1, 0, 0, 1, 0, 2, 1, 0, 2, 1] # 1=Right, 2=Left
        self.demo_command_index = -1
        self.demo_keys = [
            {pygame.K_LEFT: False, pygame.K_RIGHT: False, pygame.K_a: False, pygame.K_d: False}, # Stay still
            {pygame.K_LEFT: False, pygame.K_RIGHT: True, pygame.K_a: False, pygame.K_d: False},  # Right
            {pygame.K_LEFT: True, pygame.K_RIGHT: False, pygame.K_a: False, pygame.K_d: False}   # Left
        ]
        self.keys = {}
        self.score = 0
        self.lastwave = 1
        self.reset()

    def _load_high_score(self):
        """Load the high score table from a file or default if not found"""
        high_scores = []
        for _ in range(10):
            high_scores.append({"score": 0, "name": "..............", "highlight": False})
        try:
            with open(HIGH_SCORE_FILE) as f:
                lines = f.read().splitlines()
                count = 0
                for line in lines:
                    if count % 2 == 0:
                        score = int(line or 0)
                    else:
                        name = line or ".............."
                        high_scores.append({"score": score, "name": name, "highlight": False})
                    count += 1
                    if count > 20:
                        break
        except (OSError, ValueError):
            pass

        # Sort the high score table with the highest score at the top
        high_scores = list(reversed(sorted(high_scores, key=lambda d: d['score'])))[:10]
        return high_scores

    def _save_high_score(self):
        """Save the high scores to a file on exit"""
        try:
            with open(HIGH_SCORE_FILE, "w") as f:
                for i in range(10):
                    f.write(str(self.high_score_table[i]["score"]) + '\n')
                    f.write(str(self.high_score_table[i]["name"]) + '\n')
        except OSError:
            pass

    def _reset_wave(self):
        """reset actions that are common for all waves"""
        self.enemy_fire_wait = ENEMY_FIRE_WAIT
        self.invader_dir = 1 # Invader formation is going right (1) or left (-1)
        self.player_shots = [] # Only one player shot can exist at a time but create as a list to make modification easier
        self.player_shot_count = 0
        self.player.reset()
        self.enemy_shots = [None, None, None] # One entry for each ShotType
        if self.shot_timer == 1:
            self.shot_timer = 0 # Don't start with PLUNGER
        self.shot_timer = (self.shot_timer + (ENEMY_FIRE_WAIT % len(self.enemy_shots))) % len(self.enemy_shots) # sync shot timer to start of firing
        self.bunkers = self._build_bunkers()
        self.dead_invader = None
        self.ufo_timer = UFO_TIME
        self.skip_rolling = False
        self.skip_plunger = False
        self.shot_index = {
            ShotType.PLUNGER.value : 0,
            ShotType.SQUIGGLY.value : 0
        } # index of current shot in shot_column
        self.bass_index = 1
        self.bass_timer = 0
        self.last_shot_scan = "left"

    def reset(self):
        """Set up ready for a new game"""
        self.player = Player(self.player_img)
        self.invaders = self._build_formation(INVADER_TOP)
        self.shot_timer = 0 # Timing for which enemy shot types we will process this frame, first wave we start with a ROLLING shot
        self.ufo = UFO(self.ufo_img)
        self.lives = 3
        self.extra_life_available = True
        self.wave = 1
        self.formation_left = 0
        self.formation_right = 0
        self.death_pause = 0
        self.message = ""
        self.message_timer = 0
        self.game_over_count = 0
        self.title_count = 0
        self.hiscore_count = 0
        self.invaders_are_landing = False
        self._reset_wave()

    def _build_formation(self, invader_top):
        """Add the invaders to the formation with top row starting at invader_top"""
        invaders = []
        total_width = INVADER_COLS * INVADER_SPACING
        start_x = ((SCREEN_WIDTH - total_width) // 2) + 6
        for row in reversed(range(INVADER_ROWS)):
            if row == 0:
                frames, points, xoff = self.squid, 30, 2
            elif row in (1, 2):
                frames, points, xoff = self.crab, 20, 1
            else:
                frames, points, xoff = self.octopus, 10, 0
            for col in range(INVADER_COLS):
                x = start_x + col * INVADER_SPACING + (xoff * SCALE)
                y = invader_top + row * INVADER_SPACING
                invaders.append(Invader(frames, points, x, y, col + 1, row + 1))
        self.current_invader = invaders[0]
        return invaders

    def _build_bunkers(self):
        """Build 4 bunkers above the player then add an extra bunker structure for the ground line"""
        bunkers = []
        n = 4
        span = 45 * SCALE
        for i in range(n):
            x = (32 * SCALE) + (span * i)
            bunkers.append(Bunker(BUNKER, x, BUNKER_Y))
        bunkers.append(Bunker(GROUND, 0, SCREEN_HEIGHT - SCALE))
        return bunkers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

    def _play(self, name, loops=0):
        """Start playing a sound"""
        if _sound_ok and not self.mute and name in self.sounds:
            self.sounds[name].play(loops)

    def _stop(self, name = "all"):
        """Stop playing a sound or stop all sounds"""
        if _sound_ok and name == "all":
            pygame.mixer.stop()
        elif _sound_ok and name in self.sounds:
            self.sounds[name].stop()

    def _get_sound(self, name):
        """Look up a sound by name"""
        if _sound_ok and name in self.sounds:
            return self.sounds[name]
        return None

    def _play_bass_note(self):
        """Play one of the four bass notes in order"""
        if _sound_ok and not self.mute:
            self.sounds["bass"][self.bass_index].play()
        self.bass_index = (self.bass_index + 1) % 4

    def _invader_count(self):
        """Get the number of surviving invaders"""
        return len(self.invaders)

    def _formation_bounds(self):
        """Check the boundaries of the invader formation"""
        left = min(i.rect.left for i in self.invaders)
        right = max(i.rect.right for i in self.invaders)
        return left, right

    def _bass_interval(self):
        """Update the bass note interval based on original timings"""
        n = self._invader_count()
        interval = {0x32: 0x34, 0x2b: 0x2e, 0x24: 0x27, 0x1c: 0x22, 0x16: 0x1c, 0x11: 0x18, 0x0d: 0x15, 0x0a: 0x13, 0x08: 0x10, 0x07: 0x0e, 0x06: 0x0d, 0x05: 0x0c, 0x04: 0x0b, 0x03: 0x09, 0x02: 0x07, 0x01: 0x05}
        for i in interval:
            if n >= i:
                return interval[i] * (1 / FPS)

    def _show_message(self, text, frames = 120):
        """Display a message on screen"""
        self.message = text
        self.message_timer = frames

    def handle_events(self):
        """Handle keyboard input and other events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                    try:
                        icon = pygame.image.load('images/icon.png')
                        pygame.display.set_icon(icon)
                    except OSError:
                        pass
                if self.state != "paused" and event.key == pygame.K_p:
                    self.laststate = self.state
                    self.state = "paused"
                elif self.state == "title" or self.state == "demo" or self.state == "hiscore":
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.state = "playing"
                        self.reset()
                        self.score = 0
                        self.mute = False
                        self._show_message("PLAY  PLAYER <1>")
                elif self.state == "playing":
                    if event.key == pygame.K_SPACE or event.key == pygame.K_LCTRL:
                        self._fire_player()
                elif self.state == "paused":
                    if event.key == pygame.K_p:
                        self.state = self.laststate
                    if event.key == pygame.K_LCTRL:
                        self.state = self.laststate
                        event.key = pygame.K_p
                        pygame.event.post(event)
                elif self.state == "new_high_score":
                    if event.key == pygame.K_RETURN:
                        self.high_score_table.append({"score": self.score, "name": self.high_score_name, "highlight": True})
                        self.high_score_table = list(reversed(sorted(self.high_score_table, key=lambda d: d['score'])))[:10]
                        self.state = "hiscore"
                    elif event.key == pygame.K_BACKSPACE:
                        self.high_score_name = self.high_score_name[:-1]
                    elif len(self.high_score_name) < 12:
                        self.high_score_name += event.unicode
        return True

    def _fire_player(self, test = False):
        """Fire a player shot, only one player shot may be in flight at a time."""
        if (any(ps.friendly for ps in self.player_shots) or
            (self.dead_invader is not None) or
            self.player.wait > 2 or self.death_pause > 0):
            return False
        if not test: # If we pass test=True don't actually fire, useful for testing if we can fire during demo
            self.player_shots.append(
                Shot(self.player_shot, self.player_shot_explode, self.player.rect.left + (SCALE * 6), self.player.rect.top - (SCALE * 4),
                    (SCALE * -4), True))
            self.player_shot_count += 1
            self._play("shoot")
        return True

# ---------------------------------------------------------------------------
# Update Game Objects
# ---------------------------------------------------------------------------

    def update(self, dt):
        """Update game objects"""
        if self.state == "game_over":
            self.game_over_count += 1
            if self.game_over_count > 300:
                for hs in self.high_score_table:
                    hs["highlight"] = False
                if self.score > self.high_score_table[-1]["score"]:
                    self.state = "new_high_score"
                    self.high_score_name = ""
                else:
                    self.state = "hiscore"
                    self.title_variant = False
                    self.title_count = 0
                self.reset()
                return

        if self.state == "title":
            self.title_count += 1
            if self.title_count > TITLE_TIME:
                self.state = "demo"
                if self.demo_command_index == -1:
                    self.shot_timer = 2 # Start the first demo with a SQUIGGLY shot
                self._reset_wave()
            return

        if self.state == "hiscore":
            self.hiscore_count += 1
            if self.hiscore_count > TITLE_TIME:
                self.title_variant = not self.title_variant
                self.state = "title"
            return

        if self.state != "playing" and self.state != "demo":
            return

        self._update_player_shots()
        self._update_ufo()
        self._update_formation()
        self._update_enemy_fire()
        self._check_collisions()

        # Player death pause, update animation and pause enemy firing.
        if self.death_pause > 0:
            self.death_pause -= 1
            self.player.death_anim = (self.death_pause // 5) % 2
            if self.death_pause == 0:
                self.lives -= 1
                if self.lives > 0:
                    if self.state == "playing":
                        self.player.reset()
                        self.enemy_fire_wait = ENEMY_FIRE_WAIT
                    elif self.state == "demo":
                        self.state = "hiscore"
                        self.reset()
                else:
                    self._game_over()
            return

        if self.state == "playing" and self.extra_life_available and self.score >= EXTRA_LIFE_SCORE:
            self._play("extra_life")
            self._show_message("EXTRA LIFE")
            self.extra_life_available = False
            self.lives += 1

        
        self._update_bass(dt)

        if self.state == "playing": # Move the player based on keyboard input
            self.keys = pygame.key.get_pressed()
            self.player.update(self.keys)
        elif self.state == "demo" and self._fire_player(True): # Handle demo, slightly different order depending on which side of the screen we're on
            self.demo_command_index = (self.demo_command_index + 1) % len(self.demo_commands)
            if self.last_shot_scan == "right":
                self.player.update(self.keys)
                self._fire_player()
                self.keys = self.demo_keys[self.demo_commands[self.demo_command_index]]
            else:
                self.keys = self.demo_keys[self.demo_commands[self.demo_command_index]]
                self.player.update(self.keys)
                self._fire_player()
        else:
            self.player.update(self.keys) # Waiting to enable player in demo

        if self.message_timer > 0:
            self.message_timer -= 1
            if self.message_timer <= 0:
                self.message = ""

    def _invader_move(self, inv):
        """Move the invader"""
        step = (SCALE * 2) * self.invader_dir
        drop = False
        # Last invader steps 3 pixels when going right
        if self.invader_dir == 1 and self._invader_count() < 2:
            step = (SCALE * 3) * self.invader_dir
        x = inv.rect.x
        y = inv.rect.y
        if ((self.invader_dir > 0 and self.formation_right + step > INVADER_RIGHT) or
            (self.invader_dir < 0 and self.formation_left + step < INVADER_LEFT)):
            # Hit an edge: drop a row and reverse.
            drop = True
            y += INVADER_DROP
            x -= step
        else:
            x += step
        return x, y, drop

    def _next_invader(self, inv):
        """Get the next invader from the formation"""
        if inv == self.invaders[-1]:
            return self.invaders[0]
        else:
            return self.invaders[self.invaders.index(inv) + 1]

    def _update_formation(self):
        """Move the current invader in formation"""
        if not self.invaders or (self.player.active == True and self.player.wait > 0) or self.death_pause > 0:
            return # Don't update invaders for a while after player death

        for inv in self.invaders:
            if not inv.enabled:
                inv.enabled = True # Invaders appear one-by-one at start of wave
                return

        if self.dead_invader is not None: # Brief pause while an invader is exploding
            self.dead_invader.dead_timer -= 1
            if self.dead_invader.dead_timer < 17:
                if self.dead_invader.dead_timer <= 0 or (self.dead_invader.scan == "right" and self.dead_invader.dead_timer <= 1):
                    # Note that we remove the explosion a frame earlier if we're on the right of screen allowing slightly earlier shots
                    self.last_shot_scan = self.dead_invader.scan
                    self.dead_invader = None
                return

        inv = self.current_invader
        if self.invaders_are_landing and inv.rect.y + INVADER_DROP < self.player.rect.top:
            self.lives = 1
            self._lose_life() # Bottom row of invaders have reached the bottom of the screen, game over
            return
        inv.frame ^= 1 # Update the invader animation
        inv.rect.x, inv.rect.y, drop = self._invader_move(inv)
        if inv.rect.y >= self.player.rect.top:
            self.invaders_are_landing = True     # Indicate invaders reached the player row
            inv.frames, inv.xoff = self.squid, 2 # when reaching the player row mutate to squid
        if inv == self.invaders[-1]:
            self.formation_left, self.formation_right = self._formation_bounds()
            if drop:
                self.ufo.ready = True # Enable the UFO timer after the first drop
                self.invader_dir *= -1
        self.current_invader = self._next_invader(inv)

    def _update_player_shots(self):
        """Move the player shot"""
        for ps in self.player_shots:
            ps.update()
            if ps.alive and ps.rect.top < UFO_Y:
                ps.explode()
            if not ps.alive and (ps.exploding_count < 1 or (self._scan(ps.rect.left) == "right" and ps.exploding_count < 2)):
                # Note that we remove the explosion a frame earlier if we're on the right of screen allowing slightly earlier shots
                self.last_shot_scan = self._scan(ps.rect.left)
                self.player_shots.remove(ps)

    def _scan(self, x):
        """The original game processes each side of the screen separately. This is essential for timing of enemy shots.
        This method returns left or right depending on where 'x' is on the screen.
        """
        pixelx = x // SCALE
        width = SCREEN_WIDTH // SCALE
        # width - 128 is where the ISR would fire for the "middle" of the screen, because of the way the data was stored this was an approximation
        return "left" if pixelx < width - 128 else "right"

    def _update_enemy_fire(self):
        """Update enemy shots and check for new shots.
        
        There are three types or shot as enumerated in the ShotType class, using the naming conventions from
        https://www.computerarcheology.com/Arcade/SpaceInvaders/ they are:
        0 - ROLLING shot
        1 - PLUNGER shot
        2 - SQUIGGLY shot

        A pause in firing takes place after player death and at the start of wave.

        Each shot type is processed every 3 frames, every frame we update shot_timer which rotates from 0-2 and governs what shot types
        we can process this frame. We also check which side of the screen the shot is on using the _scan() method. Each frame can process "left"
        and "right" shots separately. 

        On a type/scan match we update the shot position and check if the shot has exploded or has finished it's explosion animation at which point
        we remove it, note that we can only have one of each type of shot on screen at a time.

        If no shot exists of the type we are checking and we haven't just removed that shot we go on to check if we can create a new shot of that type.
        We check the reload_times[] list and compare the players score to the smallest existing shot movement count. Initially the values are high so that
        only one shot is on screen but the reload times quickly fall as the player score racks up and the invaders fire more often.

        PLUNGER and SQUIGGLY shots use a list to drop shots from predictable columns and chooses the lowest invader in the column. If no invaders are in the
        column the shot type is skipped. ROLLING shots target the player directly, if the player is not below an invader and the player is to the left or right 
        of the invader formation but still on the same scan side we try and fire from column 1 or 11 as appropriate. Once those columns are gone ROLLING shots
        will only appear over the player.

        ROLLING shots skip every other attempt to fire.

        SQUIGGLY shots share processing with the UFO and they will not appear on screen at the same time.

        Once we reach the last invader in a wave, removing the PLUNGER shot object will disable any further PLUNGER shots for the rest of the wave.

        Because we check left and right separately there is some apparent pseudorandomness to the shot order but it is easily predictable, generally if
        a shot falls on the left it should pick the next type in the list and if it falls on the right it should repeat the same shot if the column is 
        available for fire.

        That is how the original 8080 code looks like it should work, however in emulation we observe the second ROLLING shot (the left of screen shot) 
        is delayed until shot_timer is 1 - so the actual processing order is as follows:

        shot_timer = 0:
        ROLLING - Right

        shot_timer = 1:
        PLUNGER - Right
        ROLLING - Left
        PLUNGER - Left

        shot_timer = 2:
        SQUIGGLY - Right
        SQUIGGLY - Left

        This could be a timing aftifact or it could be I missed something but it significantly affects the order the shots are fired. Without this the code
        would repeat ROLLING shots to the right of the screen if the player moves to destroy the right column at start of game and this effect gives them a
        bit of a break.
        """

        if self.lives < 1:
            return

        # List to check which shots we can process this frame
        shot_times = [
            [{"scan": "right", "type": ShotType.ROLLING.value}],
            [{"scan": "right", "type": ShotType.PLUNGER.value}, {"scan": "left", "type": ShotType.ROLLING.value}, {"scan": "left", "type": ShotType.PLUNGER.value}],
            [{"scan": "right", "type": ShotType.SQUIGGLY.value, }, {"scan": "left", "type": ShotType.SQUIGGLY.value, }]
        ]
        self.shot_timer = (self.shot_timer + 1) % len(shot_times) # timer advances 0, 1, 2 every frame and then starts again at 0

        if self.enemy_fire_wait > 0:
            self.enemy_fire_wait -=1
            return # Don't process enemy fire for a while at start of wave or after player death

        shot_frame = shot_times[self.shot_timer]    # Shot types and scan sides to process now
        for task in shot_frame:                     # Loop through shot types and scans
            if  task["type"] == ShotType.ROLLING.value:
                if self.skip_rolling:
                    self.skip_rolling = False
                    continue # Rolling shot skips every other attempt to fire

            if task["type"] == ShotType.PLUNGER.value and self.skip_plunger:
                continue # No plunger shots once we're down to the last invader

            if task["type"] == ShotType.SQUIGGLY.value and self.ufo.active:
                continue # UFO and squiggly shot processed in same task so skip

            es = self.enemy_shots[task["type"]] # Reassigned for readability
            if es is not None and self._scan(es.rect.x) == task["scan"]:
                es.update() # Update the position of the shot or decrease the explosion timer
                if not es.alive and es.exploding_count <= 0:
                    self.enemy_shots[task["type"]] = None # Remove the shot object
                    if es.type == ShotType.ROLLING.value:
                        self.skip_rolling = True  # Disable every other rolling shot
                    if es.type == ShotType.PLUNGER.value:
                        if self._invader_count() == 1:
                            self.skip_plunger = True  # Once we reach the last invader disable any more plunger shots
                continue # if we processed an existing shot don't attempt to fire the same shot

            # Check if we're OK to try and create a shot from the invaders
            if self.invaders and self.death_pause <= 0 and self.enemy_shots[task["type"]] is None:
                for r in self.reload_times:
                    if self.state == "demo":
                        reload_time = 8 # Reload rate during demo is always 8
                    elif self.score < r or r == -1:
                        reload_time = self.reload_times[r] # Check reload times for invaders based on player score
                        break 
                reload = []
                for s in self.enemy_shots:
                    if s is not None:
                        reload.append(s.move_count)
                if len(reload) == 0 or min(reload) >= reload_time:
                    columns = {}    # dict of columns giving lowest invader object in column
                    distance = {}   # dict of distances from player giving column
                    shooter = None
                    for inv in self.invaders:
                        col = inv.col
                        if col not in columns or inv.row > columns[col].row:
                            columns[col] = inv
                            distance[abs(inv.rect.centerx - self.player.rect.centerx)] = col
                    if task["type"] == ShotType.ROLLING.value:
                        # This shot targets the player directly
                        nearest = distance[min(distance)]
                        shooter = columns[nearest]
                        target_column = 0
                        if min(distance) <= self.player.rect.width // 2:
                            target_column = nearest
                        else:
                            # Pick the column over the player or try 1 or 11 if the player is outside the formation but on the same scan side
                            if (self.player.rect.left <= self.formation_left and
                                self._scan(self.player.rect.right) == self._scan(self.formation_left)):
                                target_column = 1
                            elif (self.player.rect.right >= self.formation_right and
                                  self._scan(self.player.rect.left) == self._scan(self.formation_right)):
                                target_column = 11
                    else:
                        # Pick next column from the list, plunger and squiggly shots advance predictably from tables
                        target_column = self.shot_column[task["type"]][self.shot_index[task["type"]]]
                        self.shot_index[task["type"]] = (self.shot_index[task["type"]] + 1) % len(self.shot_column[task["type"]])
                    shooter = columns[target_column] if target_column in columns else None
                    if shooter is not None:
                        next_invaders = [self.current_invader]
                        inv = self.current_invader
                        for _ in range(3):
                            if inv == self.invaders[-1]:
                                break
                            inv = self._next_invader(inv)
                            next_invaders.append(inv)
                        if shooter in next_invaders: # Because we delay the shot by a frame check ahead to see if we need to adjust the position
                            x, y, _ = self._invader_move(shooter)
                        else:
                            x, y = shooter.rect.x, shooter.rect.y
                        y += shooter.rect.height
                        shotx = (SCALE * 5)
                        self.enemy_shots[task["type"]] = Shot(
                            self.enemy_shot[task["type"]],
                            self.enemy_shot_explode,
                            x + shotx,
                            y + (SCALE * 6),
                            (4 * SCALE) if self._invader_count() > 8 else (5 * SCALE), 
                            False,
                            type = task["type"]
                        ) # We have a valid column, take the shot!

    def _update_ufo(self):
        """Check if we need to launch or remove a UFO and move it if it's on screen"""
        if self.ufo.ready:
            if self.ufo.active and self.shot_timer == 2:
                if self.ufo.update():
                    self._stop("ufo")
                if self.lives <= 0:
                    self.ufo.active = False
                return
            self.ufo_timer -= 1
            if self.ufo_timer <= 0 and self.enemy_shots[ShotType.SQUIGGLY.value] is None and self._invader_count() > 7:
                direction = 1 if self.player_shot_count % 2 == 0 else -1 # comes from left if player shot count is even else right
                self.ufo.spawn(direction)
                self._play("ufo", -1)
                self.ufo_timer = UFO_TIME
            if self.ufo.dead_timer > 0:
                self.ufo.dead_timer -= 1

    def _update_bass(self, dt):
        """Update the 4 bass notes, we use system time instead of frames because exact timing is not critical to gameplay"""
        if self.player.active == True and self.player.wait > 0:
            return
        self.bass_timer -= dt
        if self.bass_timer <= 0:
            self.bass_timer = self._bass_interval()
            self._play_bass_note()

    def _check_collisions(self):
        """Check obect rect structures to see if anything collided and process consequences"""
        # Player shots vs invaders.
        remaining = []
        for ps in self.player_shots:
            hit = False
            for inv in self.invaders:
                if ps.rect.colliderect(inv.rect):
                    if inv == self.current_invader: # if we hit the currently moving invader skip it
                        self.current_invader = self._next_invader(inv)
                    self.dead_invader = inv
                    self.dead_invader.scan = self._scan(ps.rect.left)
                    self.invaders.remove(inv) # invader is removed and replaced with dead_invader
                    if self.state == "playing":
                        self.score += inv.points # don't update score during demo
                    self._play("invader_killed")
                    hit = True
                    break
            if not hit:
                remaining.append(ps)
        self.player_shots = remaining

        # Player shots vs enemy shots destroy both.
        for ps in self.player_shots:
            for es in self.enemy_shots:
                if es is not None and ps.rect.colliderect(es.rect):
                    ps.explode()
                    es.explode()
                    break

        # Enemy shots vs player.
        if self.death_pause == 0:
            for es in self.enemy_shots:
                # Enemy shots only hit the player once the top of the shot reaches the base
                if es is not None and es.move_count > 1 and es.rect.top >= self.player.rect.top and es.rect.colliderect(self.player.rect):
                    es.explode()
                    self._lose_life()
                    break

        # Enemy shots vs dead invader.
        for es in self.enemy_shots:
            if es is not None and self.dead_invader is not None and es.rect.colliderect(self.dead_invader.rect):
                es.explode()
                break

        # Player shots vs UFO.
        if self.ufo.active:
            for ps in self.player_shots:
                if ps.rect.colliderect(self.ufo.rect):
                    # UFO score is based on the number of player shots.
                    # Maximum 300 score is on shot 8, 23 and every 15 shots from then onwards. Shot counts are
                    # reset at the start of a new wave.
                    ufo_score_table = [100, 50, 50, 100, 150, 100, 100, 50, 300, 100, 100, 100, 50, 150, 100]
                    ufo_score_index = (self.player_shot_count) % 15
                    self.ufo.bonus = ufo_score_table[ufo_score_index]
                    self.player_shots.remove(ps)
                    if self.state == "playing":
                        self.score += self.ufo.bonus
                    self.ufo.active = False
                    self._stop("ufo")
                    self._play("ufo_killed")
                    self.ufo.dead_timer = 90
                    break

        # All shots and the invaders erode the bunkers.
        for bunker in self.bunkers:
            for shot in self.player_shots + self.enemy_shots:
                if bunker != self.bunkers[-1] and shot is not None and shot.rect.colliderect(bunker.rect):
                    changed = bunker.damage(shot) # erode the bunker but check if we actually hit anything first
                    if changed:
                        shot.explode()
                if bunker == self.bunkers[-1] and shot is not None and shot.alive and shot.rect.bottom >= SCREEN_HEIGHT:
                    # shot reached bottom of screen which erodes like the bunkers
                    shot.rect.y -= shot.dy
                    shot.explode(immediate = True) # in the original, shots take a frame to check if they hit a bunker, in this case explode it immediately
                    bunker.damage(shot, force = True) # use the logic for eroding the bunkers but don't bother checking for hit, just erode it
                    
            for inv in self.invaders:
                if inv.rect.colliderect(bunker.rect):
                    bunker.stomp(inv)

        # Wave cleared.
        if not self.invaders:
            self.wave += 1
            invader_advance = [3, 5, 6, 6, 6, 6, 7, 7] # Move the invader formation closer to the player each wave
            invader_top = INVADER_TOP + ((invader_advance[(self.wave - 2) % len(invader_advance)]) * SCALE * 8)
            self.invaders = self._build_formation(invader_top)
            self.shot_timer = 2 # From wave 2 we start with a SQUIGGLY shot
            self._reset_wave()
            self._show_message(f"WAVE {self.wave}")

    def _lose_life(self):
        """Player got hit and died"""
        self._play("player_death")
        self.player_shots = []
        self.death_pause = 56
        self.player.dead_rect = self.player.rect.copy()

    def _game_over(self):
        """All lives and hope is lost, earth is invaded"""
        self.state = "game_over"
        self._stop()     # Stop any playing sounds
        self.mute = True # Turn off sound
        self.lastwave = self.wave
        self.player_shots = []
        if self.score > self.high_score:
            self.high_score = self.score
            self._save_high_score() # Add the pplayer name to the high score table

# ---------------------------------------------------------------------------
# Draw the screen
# ---------------------------------------------------------------------------

    def draw(self):
        """Update the screen, we create a scratch surface to draw all our objects then resize it before updating the screen"""
        self.scratch = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))

        self.scratch.fill(BLACK)

        if DEBUG: # In debug mode draw a line designating the scan sides of the screen
            pygame.draw.line(self.scratch, WHITE, (288, 0), (288, SCREEN_HEIGHT))

        for bunker in self.bunkers:
            self.scratch.blit(bunker.image, bunker.rect)

        if self.death_pause > 0: # brief animation following player death
            self.scratch.blit(self.player_dead_img[self.player.death_anim], self.player.dead_rect)
        elif self.player.wait <= 0 and self.lives > 0:
            self.scratch.blit(self.player.image, self.player.rect)

        for inv in self.invaders:
            if inv.enabled:
                self.scratch.blit(inv.image(), inv.rect)

        if self.dead_invader is not None:
            self.scratch.blit(self.enemy_dead, self.dead_invader.rect)

        for shot in self.player_shots:
            if shot is not None and shot.started:
                if shot.alive or shot.exploding_count > shot.exploding_length - 1:
                    self.scratch.blit(shot.image(), shot.rect)
                elif shot.exploding_count >= 2:
                    self.scratch.blit(shot.exploding_image, shot.exploding_rect)

        for shot in self.enemy_shots:
            if shot is not None and shot.started:
                if shot.alive or shot.exploding_count > shot.exploding_length - 1:
                    self.scratch.blit(shot.image(), shot.rect)
                elif shot.exploding_count >= 0:
                    self.scratch.blit(shot.exploding_image, shot.exploding_rect)

        if self.ufo.active:
            self.scratch.blit(self.ufo.image, self.ufo.rect)

        if self.ufo.dead_timer > 0:
            dead_rect = self.ufo_dead.get_rect()
            dead_rect.centerx = self.ufo.rect.centerx
            dead_rect.centery = self.ufo.rect.centery
            self.scratch.blit(self.ufo_dead, dead_rect)
            if self.ufo.dead_timer < 60: # Add the UFO score after a pause
                self._draw_text(str(self.ufo.bonus), self.font_small, WHITE,
                        self.ufo.rect.centerx, self.ufo.rect.centery, "center")

        if self.state == "paused":
            if SHOWPAUSE:
                self._draw_center_text("PAUSED", self.font_large, GREEN, y=63)
            self.state = self.laststate
            self.laststate = "paused"
        self._draw_hud()
        if self.state == "title":
            self._draw_title()
        elif self.state == "hiscore":
            self._draw_hiscores()
        elif self.state == "game_over":
            self._draw_game_over()
        elif self.state == "new_high_score":
            self._draw_new_high_score()
        if self.laststate == "paused":
            self.laststate = self.state
            self.state = "paused"

        if self.message: # ad hoc message to player
            self._draw_center_text(self.message, self.font_medium, RED, y=93)

        
        # resize the screen and apply CRT effect
        self._crt(self.scratch, SCREEN_WIDTH, SCREEN_HEIGHT)
        w, h = self.screen.get_size()
        s = min(w,h)
        resized = pygame.transform.smoothscale(self.scratch, (s, s))
        target_rect = self.scratch.get_rect()
        target_rect.left += (w - s) // 2
        self.screen.fill(BLACK)
        self.screen.blit(resized, target_rect)
        pygame.display.flip()

    def _crt(self, screen, w, h):
        """Cheap and cheerful simulation of pixel blur on a CRT screen"""
        # shrink then expand the screen to reduce resolution then blit to screen with lower alpha.
        surf = pygame.transform.smoothscale(screen, (w // 2, h // 2))
        surf = pygame.transform.smoothscale(surf, (w, h))
        surf.set_alpha(128)
        screen.blit(surf, (0, 0))
        # Repeat the exercise with the screen flipped to create an even pixel blur.
        surf = pygame.transform.flip(screen, True, True)
        surf = pygame.transform.smoothscale(surf, (w // 2, h // 2))
        surf = pygame.transform.smoothscale(surf, (w, h))
        surf = pygame.transform.flip(surf, True, True)
        surf.set_alpha(128)
        screen.blit(surf, (0, 0))

    def _draw_hud(self):
        """Draw score etc. in smaller font than original to make the game fit a landscape screen a little better"""
        self._draw_text("SCORE", self.font_small, WHITE, 16, 6, "left")
        self._draw_text(str(self.score), self.font_small, WHITE, 16, 30,
                        "left")
        self._draw_text("HI-SCORE", self.font_small, WHITE,
                        SCREEN_WIDTH // 2, 6, "top")
        self._draw_text(str(self.high_score), self.font_small, WHITE,
                        SCREEN_WIDTH // 2, 30, "top")
        self._draw_text("WAVE", self.font_small, WHITE,
                        SCREEN_WIDTH - 16, 6, "right")
        wave = self.wave if self.state == "playing" else self.lastwave
        self._draw_text(str(wave), self.font_small, WHITE,
                        SCREEN_WIDTH - 16, 30, "right")
        if self.state == "playing" or self.state == "paused" or self.state == "demo":
        # Lives as small cannon icons.
            for i in range(self.lives-1):
                icon = pygame.transform.scale(self.player_img,
                                            (self.player_img.get_width() // 2,
                                            self.player_img.get_height() // 2))
                self.scratch.blit(icon, ((i * 24) + 36, SCREEN_HEIGHT - 30))
            self._draw_text(str(self.lives), self.font_small, WHITE, 9, SCREEN_HEIGHT - 30, "left")

        if DEBUG:
            # Display shot count and next UFO score for debugging (or cheating)
            ufo_score_table = [100, 50, 50, 100, 150, 100, 100, 50, 300, 100, 100, 100, 50, 150, 100]
            ufo_score_index = (self.player_shot_count+1) % 15
            ufo_bonus = ufo_score_table[ufo_score_index]
            self._draw_text(f"{self.player_shot_count} {ufo_bonus}", self.font_small, WHITE,
                    SCREEN_WIDTH - 16, SCREEN_HEIGHT - 30, "right")

    def _draw_legend(self):
        """A bottom-of-screen point-value legend."""
        y = SCREEN_HEIGHT - 30
        self.scratch.blit(self.ufo_icon, (84, y+SCALE))
        self._draw_text("= ? PTS", self.font_small, WHITE, 126, y, "left")
        self.scratch.blit(self.squid_icon, (228, y))
        self._draw_text("= 30 PTS", self.font_small, WHITE, 254, y, "left")
        self.scratch.blit(self.crab_icon, (354, y))
        self._draw_text("= 20 PTS", self.font_small, WHITE, 384, y, "left")
        self.scratch.blit(self.octopus_icon, (488, y ))
        self._draw_text("= 10 PTS", self.font_small, WHITE, 518, y, "left")

    def _draw_title(self):
        """Draw an intro screen with information on game keys"""
        variant = self.title_variant
        if self.title_count >= 800:
            variant = False

        step1 = self.title_count // 10
        message1 = "PLA" if variant else "PLAY"
        length1 = len(message1) + 1 if variant else len(message1)
        x1 = SCREEN_WIDTH // 2 - SCALE * 3 if variant else SCREEN_WIDTH // 2
        step2 = max(0, self.title_count // 10 - length1 - 4)
        message2 = "SPACE"
        step3 = max(0, self.title_count // 10 - length1 - len(message2) - 8)
        message3 = "INVADERS"

        self._draw_text(message1[:min(step1, len(message1))], self.font_medium, WHITE, 
                        x1, SCREEN_HEIGHT // 2 - 190, "top")
        self._draw_center_text(message2[:min(step2, len(message2))], self.font_large, GREEN,
                               y=SCREEN_HEIGHT // 2 - 160)
        self._draw_center_text(message3[:min(step3, len(message3))], self.font_large, GREEN,
                               y=SCREEN_HEIGHT // 2 - 80)
        self._draw_center_text("PRESS ENTER / SPACE TO START", self.font_medium,
                               WHITE, y=SCREEN_HEIGHT // 2 + 40)
        self._draw_center_text("ARROWS / A,D TO MOVE   SPACE / LCTRL TO FIRE",
                               self.font_small, WHITE, y=SCREEN_HEIGHT // 2 + 80)
        self._draw_center_text("P TO PAUSE        F FOR FULL SCREEN",
                               self.font_small, WHITE, y=SCREEN_HEIGHT // 2 + 100)
        self._draw_legend()

        # Animation of squid correcting upside down 'Y'
        if variant: 
            if self.title_count >= 40 and self.title_count < 400:
                self.scratch.blit(self.upside_down_y, (SCREEN_WIDTH // 2 + SCALE * 6, SCREEN_HEIGHT // 2 - 190))
            if self.title_count >= 300 and self.title_count < 400:
                anim = (self.title_count // 4) % 2
                self.scratch.blit(self.squid[anim], (SCREEN_WIDTH - SCALE * (self.title_count - 300), SCREEN_HEIGHT // 2 - 190))
            if self.title_count >= 400 and self.title_count < 500:
                anim = (self.title_count // 4) % 2
                self.scratch.blit(self.squid_pulling_y[anim], (SCREEN_WIDTH // 2 + SCALE * (self.title_count - 400 + 6), SCREEN_HEIGHT // 2 - 190))
            if self.title_count >= 600 and self.title_count < 700:
                anim = (self.title_count // 4) % 2
                self.scratch.blit(self.squid_pushing_y[anim], (SCREEN_WIDTH - SCALE * (self.title_count - 600 + 7), SCREEN_HEIGHT // 2 - 190))
            if self.title_count >= 700 and self.title_count < 800:
                self.scratch.blit(self.squid_pushing_y[0], (SCREEN_WIDTH // 2 + SCALE * 5, SCREEN_HEIGHT // 2 - 190))

    def _draw_hiscores(self):
        """Draw the high score table"""
        variant = self.title_variant

        message = "HIGH  CCORES" if variant and self.hiscore_count < 445 else "HIGH  SCORES"

        self._draw_center_text(message, self.font_medium,
                            RED, y=SCREEN_HEIGHT // 2 - 180)
        for i in range(10):
            colour = GREEN if self.high_score_table[i]["highlight"] else WHITE
            self._draw_text(str(self.high_score_table[i]["score"]), self.font_medium,
                            colour, SCREEN_WIDTH // 2 - 24, SCREEN_HEIGHT // 2 - 120 + (i * 27), "right")
            self._draw_text(self.high_score_table[i]["name"], self.font_medium,
                            colour, SCREEN_WIDTH // 2 + 12, SCREEN_HEIGHT // 2 - 120 + (i * 27), "left")
        self._draw_legend()

        # Animation of squid blowing up 'C'
        if variant:
            if self.hiscore_count >= 300 and self.hiscore_count < 400:
                anim = (self.hiscore_count // 4) % 2
                self.scratch.blit(self.squid[anim], (SCALE * (self.hiscore_count - 294), UFO_Y))
            if self.hiscore_count >= 400 and self.hiscore_count < 460:
                self.scratch.blit(self.squid[0], (SCALE * 106, UFO_Y))
            if self.hiscore_count >= 420 and self.hiscore_count < 440:
                anim = self.hiscore_count % 4
                self.scratch.blit(self.enemy_shot[ShotType.SQUIGGLY.value][anim], (SCALE * 109, UFO_Y + SCALE * (self.hiscore_count - 420 + 8)))
            if self.hiscore_count >= 440 and self.hiscore_count < 450:
                self.scratch.blit(self.enemy_shot_explode, (SCALE * 107, SCREEN_HEIGHT // 2 - 180))
            if self.hiscore_count >= 460:
                anim = (self.hiscore_count // 4) % 2
                self.scratch.blit(self.squid[anim], (SCALE * (self.hiscore_count - 354), UFO_Y))

    def _draw_game_over(self):
        """Draw Game Over"""
        message = "GAME OVER"
        step = min(self.game_over_count // 6, len(message))
        self._draw_center_text(message[:step], self.font_large, RED, y = 60)

    def _draw_new_high_score(self):
        """Allow player to enter their name when they have a new high score"""
        self._draw_center_text("NEW  HIGH  SCORE!", self.font_medium,
                            RED, y=SCREEN_HEIGHT // 2 - 200)
        self._draw_center_text("ENTER  YOUR  NAME", self.font_medium,
                            WHITE, y=SCREEN_HEIGHT // 2 - 160)
        self._draw_center_text(self.high_score_name, self.font_medium,
                            GREEN, y=SCREEN_HEIGHT // 2 - 80)
        pygame.draw.line(self.scratch, GREEN, (SCREEN_WIDTH // 3, SCREEN_HEIGHT // 2 - 40), ((SCREEN_WIDTH // 3) * 2, SCREEN_HEIGHT // 2 - 40), 3)

    def _draw_text(self, text, font, color, x, y, align="center"):
        """Draw some text on the screen"""
        surf = font.render(text, True, color)
        rect = surf.get_rect()
        if align == "left":
            rect.topleft = (x, y)
        elif align == "right":
            rect.topright = (x, y)
        elif align == "top":
            rect.midtop = (x, y)
        else:
            rect.center = (x, y)
        self.scratch.blit(surf, rect)

    def _draw_center_text(self, text, font, color, y):
        """Draw some text in the middle of the screen"""
        self._draw_text(text, font, color, SCREEN_WIDTH // 2, y, "top")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


    def run(self):
        """Main loop"""
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            running = self.handle_events()
            self.update(dt)
            self.draw()
        self._save_high_score()
        pygame.quit()
        sys.exit()


def main():
    pygame.init()
    Game().run()


if __name__ == "__main__":
    main()
