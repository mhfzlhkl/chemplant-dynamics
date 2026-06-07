# app/components/biodiesel_component.py

from __future__ import annotations

from typing import Any, Tuple
import drawsvg as draw

from app.components.svg_primitives import Equipment, Port, metallic_gradient


def _metallic_gradient(
        grad_id,
        x1, y1, x2, y2,
        colors,
        units='userSpaceOnUse'
    ):
    return metallic_gradient(
        grad_id,
        x1, y1, x2, y2,
        colors,
        units
    )

# =========================================================
# REACTOR COLOR PALETTE
# =========================================================

REACTOR_BODY_STOPS = [
    (0.00, '  # C4C4C4'),
    (0.15, '  # FFFFFF'),
    (0.25, '  # FFFFFF'),
    (0.44, '  # DFDFDF'),
    (0.60, '  # C7C7C7'),
    (0.80, '  # A8A8A8'),
    (0.97, '  # 999999'),
    (1.00, '  # CBCBCB'),
]


# =========================================================
# REACTOR JACKET COLOR PALETTE
# ========================================================

REACTOR_JACKET_STOPS = [
    (0.00, '  # C4C4C4'),
    (0.15, '  # FFFFFF'),
    (0.25, '  # FFFFFF'),
    (0.44, '  # DFDFDF'),
    (0.60, '  # C7C7C7'),
    (0.80, '  # A8A8A8'),
    (0.97, '  # 999999'),
    (1.00, '  # CBCBCB'),
]


# ========================================================
# REACTOR FLUID COLOR PALETTE
# =========================================================

REACTOR_FLUID_STOPS = [
    (0.00, '  # C49C3E'),
    (0.15, '  # FFD069'),
    (0.26, '  # FFD992'),
    (0.38, '  # DFB248'),
    (0.6, '  # C79E3F'),
    (0.8, '  # A88534'),
    (0.97, '  # 997A2E'),
    (1.00, '  # CBA240'),
]


# =========================================================
# VALVE COLOR PALETTES
# =========================================================

VALVE_GRAY_STOPS = [
    (0.00, '  # 8F8F8F'),
    (0.15, '  # C6C6C6'),
    (0.25, '  # E0E0E0'),
    (0.52, '  # A9A9A9'),
    (0.69, '  # 979797'),
    (0.80, '  # 8E8E8E'),
    (0.92, '  # 868686'),
    (1.00, '  # 9A9A9A'),
]

VALVE_GREEN_STOPS = [
    (0.00, '  # 008239'),
    (0.15, '  # 45B667'),
    (0.25, '  # B3D8BB'),
    (0.52, '  # 009A45'),
    (0.69, '  # 00883C'),
    (0.80, '  # 008038'),
    (0.92, '  # 007935'),
    (1.00, '  # 008C3E'),
]

VALVE_YELLOW_STOPS = [
    (0.00, '  # BDBD00'),
    (0.15, '  # FFFF45'),
    (0.25, '  # FFFFB3'),
    (0.52, '  # DFDF00'),
    (0.69, '  # C7C700'),
    (0.80, '  # BCBC00'),
    (0.92, '  # B1B100'),
    (1.00, '  # CBCB00'),
]

VALVE_RED_STOPS = [
    (0.00, '  # 7D0000'),
    (0.15, '  # B14545'),
    (0.25, '  # D6B3B3'),
    (0.52, '  # 940000'),
    (0.69, '  # 840000'),
    (0.80, '  # 7C0000'),
    (0.92, '  # 750000'),
    (1.00, '  # 870000'),
]

VALVE_COLOR_SCHEMES = {
    'gray': VALVE_GRAY_STOPS,
    'normal': VALVE_GRAY_STOPS,

    'green': VALVE_GREEN_STOPS,
    'open': VALVE_GREEN_STOPS,
    'running': VALVE_GREEN_STOPS,

    'yellow': VALVE_YELLOW_STOPS,
    'warning': VALVE_YELLOW_STOPS,

    'red': VALVE_RED_STOPS,
    'closed': VALVE_RED_STOPS,
    'error': VALVE_RED_STOPS,
    'alarm': VALVE_RED_STOPS,
}

def _valve_gradient(
    grad_id: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color_scheme: str = 'gray',
    opacity: float = 1.0,
    units: str = 'userSpaceOnUse',
) -> draw.LinearGradient:
    """
    Reusable gradient untuk valve.

    color_scheme:
    - gray / normal
    - green / open / running
    - yellow / warning
    - red / closed / error / alarm
    """

    stops = VALVE_COLOR_SCHEMES.get(color_scheme, VALVE_GRAY_STOPS)

    lg = draw.LinearGradient(
        x1,
        y1,
        x2,
        y2,
        id=grad_id,
        gradientUnits=units
    )

    for offset, color in stops:
        lg.add_stop(offset, color, opacity=opacity)

    return lg


# =========================================================
# PUMP COLOR PALETTES
# =========================================================

PUMP_METAL_STOPS = [
    (0.00, '  # 686E75'),
    (0.22, '  # 9BA3AD'),
    (0.57, '  # E6E8EC'),
    (0.84, '  # CAD0D8'),
    (1.00, '  # 858C95'),
]


PUMP_INDICATOR_COLORS = {
    'normal': '  # FF0000',
    'running': '  # 00A651',
    'open': '  # 00A651',
    'warning': '  # FFC000',
    'alarm': '  # FF0000',
    'error': '  # FF0000',
    'stopped': '  # 8F8F8F',
    'off': '  # 8F8F8F',
}



def _pump_indicator_color(status: str, fallback: str = '  # FF0000') -> str:
    """
    Reusable warna indicator / blade pump.
    """
    return PUMP_INDICATOR_COLORS.get(status, fallback)


# =========================================================
# INPUT / OUTPUT ARROW COLOR SCHEMES
# =========================================================

IO_ARROW_COLORS = {
    'white': '  # FFFFFF',
    'default': '  # FFFFFF',

    'yellow': '  # FFC000',
    'warning': '  # FFC000',
    'feed': '  # FFC000',

    'blue': '  # 0070C0',
    'cooling': '  # 0070C0',
    'water': '  # 0070C0',

    'red': '  # FF0000',
    'hot': '  # FF0000',
    'alarm': '  # FF0000',
    'error': '  # FF0000',

    'green': '  # 00A651',
    'running': '  # 00A651',
    'product': '  # 00A651',
    'vent': '  # FFFFFF',
}


def _io_arrow_color(
    color_scheme: str = 'default',
    fallback: str = '  # FFFFFF'
) -> str:
    return IO_ARROW_COLORS.get(color_scheme, fallback)


Point = Tuple[float, float]


# =========================================================
# PROCESS LINE COLOR SCHEMES
# =========================================================

PROCESS_LINE_COLORS = {
    # default
    'default': '  # FFFFFF',
    'white': '  # FFFFFF',

    # process material / feed
    'oil': '  # FFC000',
    'methanol': '  # FFC000',
    'meoh': '  # FFFFFF',
    'naoh': '  # FFFFFF',

    # cooling / water
    'cooling': '  # 0070C0',
    'water': '  # 0070C0',
    'blue': '  # 0070C0',

    # hot / steam / alarm
    'hot': '  # FF0000',
    'steam': '  # FF0000',
    'red': '  # FF0000',
    'alarm': '  # FF0000',
    'error': '  # FF0000',

    # product / running
    'product': '  # FFCC53',
    'running': '  # 00A651',
    'green': '  # 00A651',

    # signal / instrument
    'signal': '  # 666666',
    'instrument': '  # 666666',
    'gray': '  # 666666',
    'grey': '  # 666666',

    # waste / drain
    'waste': '  # 7030A0',
    'drain': '  # 7030A0',
    'purple': '  # 7030A0',

    # neutral / air
    'air': '  # A6A6A6',
    'neutral': '  # A6A6A6',
}


def process_line_color(
    color_scheme: str = 'default',
    fallback: str = '  # 000000'
) -> str:
    """
    Resolve process line color from a color scheme.
    """
    return PROCESS_LINE_COLORS.get(color_scheme, fallback)


# REACTOR BODY
class ReactorBody(Equipment):
    def __init__(
            self,
            id: str,
            x: float = 0, # 563.498px
            y: float = 0, # 138.863px
            status: str = 'normal',
    ): super().__init__(
        id=id,
        x=x,
        y=y,
        status=status,
        ports={
            'inlet-1': Port(10.22, 23.0),
            'inlet-2': Port(30.5, 9.0),
            'outlet': Port(77.14, 301.5),
            'vent': Port(129.1, 11.8),
        },
    )

    def render(self) -> draw.Group:
        g = draw.Group(
            id=self.id,
            class_=f'equipment reactor body {self.status}',
            transform=f'translate({self.x}, {self.y})',
        )

        # Cylindrical Body
        '''
        <svg xmlns="http://www.w3.org/2000/svg" width="155" height="302" viewBox="0 0 155 302" fill="none">
            <path d="M0 263C6.8 285.3 39.2 301.5 77.1 301.5C115 301.5 147.5 285.3 154.3 263V38.6C147.5 16.2 115 0 77.1 0C39.2 0 6.8 16.2 0 38.6V263Z" fill="url(  # paint0_linear_1_82)"/>
            <defs>
                <linearGradient id="paint0_linear_1_82" x1="154.3" y1="0" x2="0" y2="0" gradientUnits="userSpaceOnUse">
                <stop stop-color="  # C4C4C4"/>
                <stop offset="0.15" stop-color="white"/>
                <stop offset="0.25" stop-color="white"/>
                <stop offset="0.44" stop-color="  # DFDFDF"/>
                <stop offset="0.6" stop-color="  # C7C7C7"/>
                <stop offset="0.8" stop-color="  # A8A8A8"/>
                <stop offset="0.97" stop-color="  # 999999"/>
                <stop offset="1" stop-color="  # CBCBCB"/>
                </linearGradient>
            </defs>
        </svg>
        '''

        # Gradient Fill
        g.append(_metallic_gradient(
            grad_id='gradient_reactor_cylinder',
            x1=154.3, y1=0, x2=0, y2=0,
            colors=REACTOR_BODY_STOPS,
        ))

        g.append(draw.Path(
            id='reactor-cylinder',
            d="M0 263C6.8 285.3 39.2 301.5 77.1 301.5C115 301.5 147.5 285.3 154.3 263V38.6C147.5 16.2 115 0 77.1 0C39.2 0 6.8 16.2 0 38.6V263Z",
            fill='url(  # gradient_reactor_cylinder)',
        ))

        return g


# Reactor Fluid

'''
<svg xmlns="http://www.w3.org/2000/svg" width="150" height="262" viewBox="0 0 150 262" fill="none">
<path d="M0.2 0H149.2L149.9 225.5C149.9 225.5 146.7 235.4 137.9 242.2C120.3 255.6 97.8 262.2 74.7 262C52.3 261.8 26.8 254.2 14.7 244.2C2.6 234.2 0 226 0 226L0.2 0Z" fill="url(  # paint0_linear_1_99)"/>
<defs>
    <linearGradient id="paint0_linear_1_99" x1="149.9" y1="0" x2="0" y2="0" gradientUnits="userSpaceOnUse">
    <stop stop-color="  # C49C3E" stop-opacity="0.3"/>
    <stop offset="0.15" stop-color="  # FFD069" stop-opacity="0.3"/>
    <stop offset="0.26" stop-color="  # FFD992" stop-opacity="0.3"/>
    <stop offset="0.38" stop-color="  # DFB248" stop-opacity="0.3"/>
    <stop offset="0.6" stop-color="  # C79E3F" stop-opacity="0.3"/>
    <stop offset="0.8" stop-color="  # A88534" stop-opacity="0.3"/>
    <stop offset="0.97" stop-color="  # 997A2E" stop-opacity="0.3"/>
    <stop offset="1" stop-color="  # CBA240" stop-opacity="0.3"/>
    </linearGradient>
</defs>
</svg>

'''

# REACTOR FLUID LAYER
class ReactorFluidLayer:
    WALL_THICKNESS = 2

    # Mengikuti ukuran asli ReactorBody, bukan SVG fluid lama
    BODY_RIGHT = 154.3
    BODY_BOTTOM = 301.5
    BODY_TOP_DOME_END = 38.6
    BODY_BOTTOM_DOME_START = 263.0
    BODY_CENTER_X = 77.1

    def __init__(
        self,
        id: str,
        body: ReactorBody,
        fluid_level: float = 0.5,
        fluid_opacity: float = 0.3
    ):
        self.id = id
        self.body = body
        self.fluid_level = max(0.0, min(1.0, fluid_level))
        self.fluid_opacity = fluid_opacity

    # =========================================================
    # Column geometry
    # Pakai body left/right/top/bottom, bukan body.width
    # =========================================================

    @property
    def _column_left(self) -> float:
        return self.body.x

    @property
    def _column_right(self) -> float:
        return self.body.x + self.BODY_RIGHT

    @property
    def _column_top(self) -> float:
        return self.body.y

    @property
    def _column_bottom(self) -> float:
        return self.body.y + self.BODY_BOTTOM

    @property
    def _column_center_x(self) -> float:
        return self.body.x + self.BODY_CENTER_X

    @property
    def _fluid_left(self) -> float:
        return self._column_left + self.WALL_THICKNESS

    @property
    def _fluid_right(self) -> float:
        return self._column_right - self.WALL_THICKNESS

    @property
    def _fluid_top(self) -> float:
        # Fluid mulai dari area silinder lurus,
        # bukan dari top dome column
        return self.body.y + self.BODY_TOP_DOME_END + self.WALL_THICKNESS

    @property
    def _fluid_bottom(self) -> float:
        return self._column_bottom - self.WALL_THICKNESS

    @property
    def _fluid_dome_start_y(self) -> float:
        return self.body.y + self.BODY_BOTTOM_DOME_START

    @property
    def _fluid_width(self) -> float:
        return self._fluid_right - self._fluid_left

    @property
    def _fluid_height(self) -> float:
        return self._fluid_bottom - self._fluid_top

    # =========================================================
    # Gradient emas transparan sesuai SVG fluid
    # =========================================================

    def _gold_gradient(self) -> draw.LinearGradient:
        grad_id = f'{self.id}-gold-gradient'

        gradient = draw.LinearGradient(
            x1=self._fluid_right,
            y1=self._fluid_top,
            x2=self._fluid_left,
            y2=self._fluid_top,
            id=grad_id,
            gradientUnits='userSpaceOnUse'
        )

        gradient.add_stop(0.00, '  # C49C3E', opacity=self.fluid_opacity)
        gradient.add_stop(0.15, '  # FFD069', opacity=self.fluid_opacity)
        gradient.add_stop(0.26, '  # FFD992', opacity=self.fluid_opacity)
        gradient.add_stop(0.38, '  # DFB248', opacity=self.fluid_opacity)
        gradient.add_stop(0.60, '  # C79E3F', opacity=self.fluid_opacity)
        gradient.add_stop(0.80, '  # A88534', opacity=self.fluid_opacity)
        gradient.add_stop(0.97, '  # 997A2E', opacity=self.fluid_opacity)
        gradient.add_stop(1.00, '  # CBA240', opacity=self.fluid_opacity)

        return gradient

    # =========================================================
    # Clip path fluid mengikuti dome bawah ReactorBody
    # =========================================================

    def _tank_clip(self) -> draw.ClipPath:
        clip = draw.ClipPath(id=f'{self.id}-clip')

        x = self.body.x
        y = self.body.y
        wt = self.WALL_THICKNESS

        left = x + wt
        right = x + self.BODY_RIGHT - wt
        top = y + self.BODY_TOP_DOME_END + wt

        # titik awal dome bawah column
        dome_y = y + self.BODY_BOTTOM_DOME_START

        # titik bawah dome dibuat sedikit naik karena ada wall thickness
        bottom_y = y + self.BODY_BOTTOM - wt

        # control point mengikuti path reactor-cylinder:
        # M0 263
        # C6.8 285.3 39.2 301.5 77.1 301.5
        # C115 301.5 147.5 285.3 154.3 263
        path_d = (
            f"M{left} {top} "
            f"H{right} "
            f"V{dome_y} "

            # kanan turun ke bawah tengah
            f"C{x + 147.5 - wt} {y + 285.3} "
            f"{x + 115.0} {bottom_y} "
            f"{x + 77.1} {bottom_y} "

            # bawah tengah ke kiri naik
            f"C{x + 39.2} {bottom_y} "
            f"{x + 6.8 + wt} {y + 285.3} "
            f"{left} {dome_y} "

            f"V{top} "
            f"Z"
        )

        clip.append(draw.Path(d=path_d))
        return clip

    # =========================================================
    # Wave
    # =========================================================

    def _wave_path(
        self,
        start_x: float,
        surface_y: float,
        width: float,
        wave_length: float,
        wave_height: float,
        bottom_y: float,
        fill: str,
        opacity: float = 1.0
    ) -> draw.Path:
        end_x = start_x + width
        path_d = f"M{start_x} {surface_y} "

        x = start_x
        toggle = -1

        while x < end_x:
            control_x = x + wave_length / 4
            end_segment_x = x + wave_length / 2

            path_d += (
                f"Q{control_x} {surface_y + toggle * wave_height} "
                f"{end_segment_x} {surface_y} "
            )

            x += wave_length / 2
            toggle *= -1

        path_d += (
            f"L{end_x} {bottom_y} "
            f"L{start_x} {bottom_y} "
            f"Z"
        )

        return draw.Path(
            d=path_d,
            fill=fill,
            fill_opacity=opacity
        )

    # =========================================================
    # Render
    # =========================================================

    def render(self) -> draw.Group:
        g = draw.Group(id=self.id, class_='reactor-fluid-layer')

        g.append(self._tank_clip())
        g.append(self._gold_gradient())

        fluid = draw.Group(
            clip_path=f'url(  # {self.id}-clip)',
            class_='reactor-fluid'
        )

        gold_fill = f'url(  # {self.id}-gold-gradient)'

        surface_y = self._fluid_bottom - self._fluid_height * self.fluid_level

        # Tambah sedikit ke bawah supaya dome bawah selalu penuh setelah clip
        bottom_y = self._column_bottom + 10

        # Base fluid fill
        fluid.append(draw.Rectangle(
            self._fluid_left,
            surface_y,
            self._fluid_width,
            bottom_y - surface_y,
            fill=gold_fill,
            fill_opacity=1.0
        ))

        # Highlight permukaan
        highlight_id = f'{self.id}-surface-highlight'

        highlight = draw.LinearGradient(
            x1=0,
            y1=surface_y,
            x2=0,
            y2=surface_y + 22,
            id=highlight_id,
            gradientUnits='userSpaceOnUse'
        )

        highlight.add_stop(0.0, '  # FFFFFF', opacity=0.35)
        highlight.add_stop(1.0, '  # FFFFFF', opacity=0.0)

        g.append(highlight)

        fluid.append(draw.Rectangle(
            self._fluid_left,
            surface_y,
            self._fluid_width,
            22,
            fill=f'url(  # {highlight_id})'
        ))

        # Wave mengikuti jarak left/right fluid
        ext = self._fluid_width * 1.7
        wave_start = self._fluid_left - ext
        wave_total = self._fluid_width + ext * 2

        wave_length = self._fluid_width * 0.65
        wave_height = self._fluid_height * 0.02

        w1 = self._wave_path(
            start_x=wave_start,
            surface_y=surface_y,
            width=wave_total,
            wave_length=wave_length,
            wave_height=wave_height,
            bottom_y=bottom_y,
            fill=gold_fill,
            opacity=1.0
        )
        w1.args['class'] = 'fluid-wave-1'
        fluid.append(w1)

        w2 = self._wave_path(
            start_x=wave_start,
            surface_y=surface_y + 3,
            width=wave_total,
            wave_length=wave_length * 0.9,
            wave_height=wave_height * 0.8,
            bottom_y=bottom_y,
            fill=gold_fill,
            opacity=0.8
        )
        w2.args['class'] = 'fluid-wave-2'
        fluid.append(w2)

        w3 = self._wave_path(
            start_x=wave_start,
            surface_y=surface_y + 6,
            width=wave_total,
            wave_length=wave_length * 1.2,
            wave_height=wave_height * 0.6,
            bottom_y=bottom_y,
            fill=gold_fill,
            opacity=0.65
        )
        w3.args['class'] = 'fluid-wave-3'
        fluid.append(w3)

        main_wave = self._wave_path(
            start_x=wave_start,
            surface_y=surface_y,
            width=wave_total,
            wave_length=wave_length,
            wave_height=wave_height,
            bottom_y=surface_y + 10,
            fill=gold_fill,
            opacity=1.0
        )
        main_wave.args['class'] = 'fluid-wave-main'
        fluid.append(main_wave)

        g.append(fluid)
        return g


# REACTOR JACKET
class ReactorJacket(Equipment):
    def __init__(
            self,
            id: str,
            x: float = 0, # 553.327px
            y: float = 0, # 176.657px
            status: str = 'normal',
    ): super().__init__(
        id=id,
        x=x,
        y=y,
        status=status,
        ports={
            'inlet': Port(0, 191.84),
            'outlet': Port(174.6, 37.84),
        },
    )

    def render(self) -> draw.Group:
        g = draw.Group(
            id=self.id,
            class_=f'equipment reactor jacket {self.status}',
            transform=f'translate({self.x}, {self.y})',
        )

        # Reactor Jacket
        '''
        <svg xmlns="http://www.w3.org/2000/svg" width="175" height="273" viewBox="0 0 175 273" fill="none">
        <path d="M15 0H159.6C167.9 0 174.6 6.7 174.6 15V211.4C174.6 219.7 174.1 231.7 168.7 240.1C159.9 253.8 138.5 272.8 87.9 273C37 273.1 15.2 253.8 6.1 240C0.6 231.6 0 219.7 0 211.4V15C0 6.7 6.7 0 15 0Z" fill="url(  # paint0_linear_1_79)"/>
        <defs>
            <linearGradient id="paint0_linear_1_79" x1="0" y1="0" x2="0" y2="273" gradientUnits="userSpaceOnUse">
            <stop stop-color="  # C4C4C4"/>
            <stop offset="0.15" stop-color="white"/>
            <stop offset="0.25" stop-color="white"/>
            <stop offset="0.44" stop-color="  # DFDFDF"/>
            <stop offset="0.6" stop-color="  # C7C7C7"/>
            <stop offset="0.8" stop-color="  # A8A8A8"/>
            <stop offset="0.97" stop-color="  # 999999"/>
            <stop offset="1" stop-color="  # CBCBCB"/>
            </linearGradient>
        </defs>
        </svg>
        '''

        # Gradient Fill
        g.append(_metallic_gradient(
            grad_id='gradient_reactor_jacket',
            x1=0, y1=0, x2=0, y2=273,
            colors=REACTOR_JACKET_STOPS,
        ))

        g.append(draw.Path(
            id='reactor-jacket',
            d="M15 0H159.6C167.9 0 174.6 6.7 174.6 15V211.4C174.6 219.7 174.1 231.7 168.7 240.1C159.9 253.8 138.5 272.8 87.9 273C37 273.1 15.2 253.8 6.1 240C0.6 231.6 0 219.7 0 211.4V15C0 6.7 6.7 0 15 0Z",
            fill='url(  # gradient_reactor_jacket)',
        ))

        return g


# STIRRED
class Stirred(Equipment):
    def __init__(
            self,
            id: str,
            x: float = 0,
            y: float = 0,
            status: str = 'normal',
    ): super().__init__(
        id=id,
        x=x,
        y=y,
        status=status,
    )

    def render(self) -> draw.Group:
        g = draw.Group(
            id=self.id,
            class_=f'equipment stirred-reactor {self.status}',
            transform=f'translate({self.x}, {self.y})',
        )



        # Motor
        '''
        <svg xmlns="http://www.w3.org/2000/svg" width="50" height="117" viewBox="0 0 50 117" fill="none">
        <path d="M14.301 73.1566H35.201V116.557H14.301V73.1566Z" fill="url(  # paint0_linear_31_998)"/>
        <path d="M3.45856 11.4612H46.0586V72.6612H3.45856V11.4612Z" fill="url(  # paint1_linear_31_998)"/>
        <path d="M9.76965 0H39.6697V11.5H9.76965V0Z" fill="url(  # paint2_linear_31_998)"/>
        <path d="M3.45856 65.901H46.0586V75.001H3.45856V65.901Z" fill="url(  # paint3_linear_31_998)"/>
        <path d="M1.7 71.6428H47.7C48.6 71.6428 49.4 72.5428 49.4 73.7428V78.7428C49.4 79.9428 48.6 80.9428 47.7 80.9428H1.7C0.7 80.9428 0 79.9428 0 78.7428V73.7428C0 72.5428 0.7 71.6428 1.7 71.6428Z" fill="url(  # paint4_linear_31_998)"/>
        <path d="M1.7 71.6428H47.7C48.6 71.6428 49.4 72.5428 49.4 73.7428V78.7428C49.4 79.9428 48.6 80.9428 47.7 80.9428H1.7C0.7 80.9428 0 79.9428 0 78.7428V73.7428C0 72.5428 0.7 71.6428 1.7 71.6428Z" fill="url(  # paint5_linear_31_998)"/>
        <defs>
            <linearGradient id="paint0_linear_31_998" x1="35.201" y1="73.1566" x2="14.301" y2="73.1566" gradientUnits="userSpaceOnUse">
            <stop stop-color="  # 5C5C5C"/>
            <stop offset="0.15" stop-color="  # 8A8A8A"/>
            <stop offset="0.25" stop-color="  # C6C6C6"/>
            <stop offset="0.52" stop-color="  # 6D6D6D"/>
            <stop offset="0.69" stop-color="  # 616161"/>
            <stop offset="0.8" stop-color="  # 5B5B5B"/>
            <stop offset="0.92" stop-color="  # 555555"/>
            <stop offset="1" stop-color="  # 636363"/>
            </linearGradient>
            <linearGradient id="paint1_linear_31_998" x1="46.0586" y1="11.4612" x2="3.45856" y2="11.4612" gradientUnits="userSpaceOnUse">
            <stop stop-color="  # 5C5C5C"/>
            <stop offset="0.15" stop-color="  # 8A8A8A"/>
            <stop offset="0.25" stop-color="  # C6C6C6"/>
            <stop offset="0.52" stop-color="  # 6D6D6D"/>
            <stop offset="0.69" stop-color="  # 616161"/>
            <stop offset="0.8" stop-color="  # 5B5B5B"/>
            <stop offset="0.92" stop-color="  # 555555"/>
            <stop offset="1" stop-color="  # 636363"/>
            </linearGradient>
            <linearGradient id="paint2_linear_31_998" x1="39.6697" y1="0" x2="9.76965" y2="0" gradientUnits="userSpaceOnUse">
            <stop stop-color="  # 5C5C5C"/>
            <stop offset="0.15" stop-color="  # 8A8A8A"/>
            <stop offset="0.25" stop-color="  # C6C6C6"/>
            <stop offset="0.52" stop-color="  # 6D6D6D"/>
            <stop offset="0.69" stop-color="  # 616161"/>
            <stop offset="0.8" stop-color="  # 5B5B5B"/>
            <stop offset="0.92" stop-color="  # 555555"/>
            <stop offset="1" stop-color="  # 636363"/>
            </linearGradient>
            <linearGradient id="paint3_linear_31_998" x1="46.0586" y1="65.901" x2="3.45856" y2="65.901" gradientUnits="userSpaceOnUse">
            <stop stop-color="  # 5C5C5C"/>
            <stop offset="0.15" stop-color="  # 8A8A8A"/>
            <stop offset="0.25" stop-color="  # C6C6C6"/>
            <stop offset="0.52" stop-color="  # 6D6D6D"/>
            <stop offset="0.69" stop-color="  # 616161"/>
            <stop offset="0.8" stop-color="  # 5B5B5B"/>
            <stop offset="0.92" stop-color="  # 555555"/>
            <stop offset="1" stop-color="  # 636363"/>
            </linearGradient>
            <linearGradient id="paint4_linear_31_998" x1="49.4" y1="71.6428" x2="0" y2="71.6428" gradientUnits="userSpaceOnUse">
            <stop stop-color="  # 5C5C5C"/>
            <stop offset="0.15" stop-color="  # 8A8A8A"/>
            <stop offset="0.25" stop-color="  # C6C6C6"/>
            <stop offset="0.52" stop-color="  # 6D6D6D"/>
            <stop offset="0.69" stop-color="  # 616161"/>
            <stop offset="0.8" stop-color="  # 5B5B5B"/>
            <stop offset="0.92" stop-color="  # 555555"/>
            <stop offset="1" stop-color="  # 636363"/>
            </linearGradient>
            <linearGradient id="paint5_linear_31_998" x1="49.4" y1="71.6428" x2="0" y2="71.6428" gradientUnits="userSpaceOnUse">
            <stop stop-color="  # 5C5C5C"/>
            <stop offset="0.15" stop-color="  # 8A8A8A"/>
            <stop offset="0.25" stop-color="  # C6C6C6"/>
            <stop offset="0.52" stop-color="  # 6D6D6D"/>
            <stop offset="0.69" stop-color="  # 616161"/>
            <stop offset="0.8" stop-color="  # 5B5B5B"/>
            <stop offset="0.92" stop-color="  # 555555"/>
            <stop offset="1" stop-color="  # 636363"/>
            </linearGradient>
        </defs>
        </svg>

        '''

        g.append(draw.Path(
            d="M3.45856 11.4612H46.0586V72.6612H3.45856V11.4612Z",
            fill="url(  # paint1_linear_31_998)"
        ))

        g.append(draw.Path(
            d="M3.45856 11.4612H46.0586V72.6612H3.45856V11.4612Z",
            fill="url(  # paint1_linear_31_998)"
        ))

        g.append(draw.Path(
            d="M9.76965 0H39.6697V11.5H9.76965V0Z",
            fill="url(  # paint2_linear_31_998)"
        ))

        g.append(draw.Path(
            d="M3.45856 65.901H46.0586V75.001H3.45856V65.901Z",
            fill="url(  # paint3_linear_31_998)"
        ))

        g.append(draw.Path(
            d="M1.7 71.6428H47.7C48.6 71.6428 49.4 72.5428 49.4 73.7428V78.7428C49.4 79.9428 48.6 80.9428 47.7 80.9428H1.7C0.7 80.9428 0 79.9428 0 78.7428V73.7428C0 72.5428 0.7 71.6428 1.7 71.6428Z",
            fill="url(  # paint4_linear_31_998)"
        ))

        g.append(draw.Path(
            d="M1.7 71.6428H47.7C48.6 71.6428 49.4 72.5428 49.4 73.7428V78.7428C49.4 79.9428 48.6 80.9428 47.7 80.9428H1.7C0.7 80.9428 0 79.9428 0 78.7428V73.7428C0 72.5428 0.7 71.6428 1.7 71.6428Z",
            fill="url(  # paint5_linear_31_998)"
        ))

        g.append(draw.Path(
            d="M0 0H15.7V241.5H0V0Z",
            fill="url(  # paint0_linear_31_993)"
        ))





        return g


# REACTOR JACKET FLUID LAYER
class ReactorJacketFluidLayer:
    WALL_THICKNESS = 2

    # Reference viewBox dari SVG fluid jacket
    VIEWBOX_WIDTH = 170
    VIEWBOX_HEIGHT = 268

    # Reference geometry dari ReactorJacket SVG asli
    # ReactorJacket path:
    # width sekitar 174.6, height 273
    JACKET_RIGHT = 174.6
    JACKET_BOTTOM = 273.0

    def __init__(
        self,
        id: str,
        jacket: ReactorJacket,
        fluid_opacity: float = 1.0
    ):
        self.id = id
        self.jacket = jacket
        self.fluid_opacity = fluid_opacity

    # =========================================================
    # Jacket geometry
    # Mengikuti left/right/top/bottom jacket,
    # bukan width/height eksplisit fluid
    # =========================================================

    @property
    def _jacket_left(self) -> float:
        return self.jacket.x

    @property
    def _jacket_right(self) -> float:
        return self.jacket.x + self.JACKET_RIGHT

    @property
    def _jacket_top(self) -> float:
        return self.jacket.y

    @property
    def _jacket_bottom(self) -> float:
        return self.jacket.y + self.JACKET_BOTTOM

    @property
    def _fluid_left(self) -> float:
        return self._jacket_left + self.WALL_THICKNESS

    @property
    def _fluid_right(self) -> float:
        return self._jacket_right - self.WALL_THICKNESS

    @property
    def _fluid_top(self) -> float:
        return self._jacket_top + self.WALL_THICKNESS

    @property
    def _fluid_bottom(self) -> float:
        return self._jacket_bottom - self.WALL_THICKNESS

    @property
    def _fluid_width(self) -> float:
        return self._fluid_right - self._fluid_left

    @property
    def _fluid_height(self) -> float:
        return self._fluid_bottom - self._fluid_top

    @property
    def _sx(self) -> float:
        return self._fluid_width / self.VIEWBOX_WIDTH

    @property
    def _sy(self) -> float:
        return self._fluid_height / self.VIEWBOX_HEIGHT

    def _x(self, value: float) -> float:
        return self._fluid_left + value * self._sx

    def _y(self, value: float) -> float:
        return self._fluid_top + value * self._sy

    # =========================================================
    # Gradient cooling fluid
    # Sesuai SVG:
    # <linearGradient x1="0" y1="0" x2="0" y2="267.402">
    #   red -> blue
    # </linearGradient>
    # =========================================================

    def _cooling_gradient(self) -> draw.LinearGradient:
        grad_id = f'{self.id}-cooling-gradient'

        gradient = draw.LinearGradient(
            x1=self._x(0),
            y1=self._y(0),
            x2=self._x(0),
            y2=self._y(267.402),
            id=grad_id,
            gradientUnits='userSpaceOnUse'
        )

        gradient.add_stop(0.00, '  # FF0000', opacity=self.fluid_opacity)
        gradient.add_stop(0.84, '  # 0070C0', opacity=self.fluid_opacity)

        return gradient

    # =========================================================
    # Fluid path
    # Path SVG fluid jacket diskalakan mengikuti jacket
    # =========================================================

    def _fluid_path(self) -> draw.Path:
        fill = f'url(  # {self.id}-cooling-gradient)'

        path_d = (
            f"M{self._x(15)} {self._y(0)} "
            f"H{self._x(154.1)} "

            f"C{self._x(162.4)} {self._y(0)} "
            f"{self._x(169.1)} {self._y(6.7)} "
            f"{self._x(169.1)} {self._y(15)} "

            f"V{self._y(206.8)} "

            f"C{self._x(169.1)} {self._y(215.1)} "
            f"{self._x(168.7)} {self._y(227)} "
            f"{self._x(163.2)} {self._y(235.5)} "

            f"C{self._x(154.6)} {self._y(248.9)} "
            f"{self._x(133.8)} {self._y(267.2)} "
            f"{self._x(85.1)} {self._y(267.4)} "

            f"C{self._x(36.2)} {self._y(267.6)} "
            f"{self._x(15)} {self._y(248.9)} "
            f"{self._x(6.1)} {self._y(235.4)} "

            f"C{self._x(0.6)} {self._y(227)} "
            f"{self._x(0)} {self._y(215.1)} "
            f"{self._x(0)} {self._y(206.8)} "

            f"V{self._y(15)} "

            f"C{self._x(0)} {self._y(6.7)} "
            f"{self._x(6.7)} {self._y(0)} "
            f"{self._x(15)} {self._y(0)} "

            f"Z"
        )

        return draw.Path(
            id=f'{self.id}-path',
            d=path_d,
            fill=fill,
        )

    def render(self) -> draw.Group:
        g = draw.Group(
            id=self.id,
            class_='reactor-jacket-fluid-layer'
        )

        g.append(self._cooling_gradient())
        g.append(self._fluid_path())

        return g


# CONTROL VALVE
class Valve(Equipment):
    WIDTH = 45
    HEIGHT = 43

    def __init__(
        self,
        id: str,
        x: float = 0,
        y: float = 0,
        status: str = 'normal',
        color_scheme: str | None = None,
        opacity: float = 1.0,
        scale: float = 1.0,
        rotation: float = 0.0,
    ):
        super().__init__(
            id=id,
            x=x,
            y=y,
            status=status,
            ports={
                # Port utama mengikuti posisi valve body
                'left': Port(0, 33.72),
                'right': Port(44.69, 33.72),

                # Optional port untuk handle/stem
                'top': Port(22.33, 0),
                'bottom': Port(22.33, 42.02),
                'center': Port(22.33, 33.72),
            },
        )

        # Jika color_scheme tidak diisi, pakai status
        self.color_scheme = color_scheme or status
        self.opacity = opacity
        self.scale = scale
        self.rotation = rotation

    def _gradient_ids(self) -> dict[str, str]:
        return {
            'stem': f'{self.id}-gradient-stem',
            'right': f'{self.id}-gradient-right',
            'left': f'{self.id}-gradient-left',
            'handle': f'{self.id}-gradient-handle',
        }

    def _append_gradients(self, g: draw.Group) -> None:
        ids = self._gradient_ids()
        scheme = self.color_scheme

        # paint0 - stem vertical kecil
        g.append(_valve_gradient(
            grad_id=ids['stem'],
            x1=20.466,
            y1=12.6282,
            x2=24.266,
            y2=12.6282,
            color_scheme=scheme,
            opacity=self.opacity,
        ))

        # paint1 - segitiga kanan
        g.append(_valve_gradient(
            grad_id=ids['right'],
            x1=44.6915,
            y1=25.4223,
            x2=22.3915,
            y2=25.4223,
            color_scheme=scheme,
            opacity=self.opacity,
        ))

        # paint2 - segitiga kiri
        g.append(_valve_gradient(
            grad_id=ids['left'],
            x1=0.0000190735,
            y1=25.4223,
            x2=22.3,
            y2=25.4223,
            color_scheme=scheme,
            opacity=self.opacity,
        ))

        # paint3 - handle dome atas
        g.append(_valve_gradient(
            grad_id=ids['handle'],
            x1=38.4335,
            y1=0,
            x2=6.23352,
            y2=0,
            color_scheme=scheme,
            opacity=self.opacity,
        ))

    def render(self) -> draw.Group:
        transform_parts = [
            f'translate({self.x}, {self.y})'
        ]

        if self.rotation:
            # Rotate around visual center valve
            transform_parts.append(
                f'rotate({self.rotation}, {self.WIDTH / 2}, {self.HEIGHT / 2})'
            )

        if self.scale != 1.0:
            transform_parts.append(f'scale({self.scale})')

        g = draw.Group(
            id=self.id,
            class_=f'equipment valve {self.status}',
            transform=' '.join(transform_parts),
        )

        self._append_gradients(g)
        ids = self._gradient_ids()

        # Stem
        g.append(draw.Path(
            d="M24.266 12.6282H20.466V33.7282H24.266V12.6282Z",
            fill=f"url(  # {ids['stem']})",
        ))

        # Right valve body
        g.append(draw.Path(
            d="M44.6915 25.4223V42.0223L22.3915 33.7223L44.6915 25.4223Z",
            fill=f"url(  # {ids['right']})",
        ))

        # Left valve body
        g.append(draw.Path(
            d="M1.90735e-05 25.4223V42.0223L22.3 33.7223L1.90735e-05 25.4223Z",
            fill=f"url(  # {ids['left']})",
        ))

        # Top handle
        g.append(draw.Path(
            d="M6.23352 16C6.23352 7.10002 13.4335 1.52588e-05 22.3335 1.52588e-05C31.2335 1.52588e-05 38.4335 7.10002 38.4335 16H6.23352Z",
            fill=f"url(  # {ids['handle']})",
        ))

        return g


# MANUAL VALVE EQUIPMENT
class ManualValve(Equipment):
    WIDTH = 45
    HEIGHT = 31

    def __init__(
        self,
        id: str,
        x: float = 0,
        y: float = 0,
        status: str = 'normal',
        color_scheme: str | None = None,
        opacity: float = 1.0,
        scale: float = 1.0,
        rotation: float = 0.0,
    ):
        super().__init__(
            id=id,
            x=x,
            y=y,
            status=status,
            ports={
                # koneksi pipa kiri-kanan
                'left': Port(0, 22.54),
                'right': Port(44.6915, 22.54),

                # optional reference
                'center': Port(22.33, 22.54),
                'top': Port(22.33, 0),
                'bottom': Port(22.33, 30.8419),
            },
        )

        self.color_scheme = color_scheme or status
        self.opacity = opacity
        self.scale = scale
        self.rotation = rotation

    def _gradient_ids(self) -> dict[str, str]:
        return {
            'stem': f'{self.id}-gradient-stem',
            'left': f'{self.id}-gradient-left',
            'right': f'{self.id}-gradient-right',
            'handle': f'{self.id}-gradient-handle',
        }

    def _append_gradients(self, g: draw.Group) -> None:
        ids = self._gradient_ids()
        scheme = self.color_scheme

        # paint0 - stem tengah
        g.append(_valve_gradient(
            grad_id=ids['stem'],
            x1=24.2256,
            y1=2.32678,
            x2=20.4256,
            y2=2.32678,
            color_scheme=scheme,
            opacity=self.opacity,
        ))

        # paint1 - body kiri
        g.append(_valve_gradient(
            grad_id=ids['left'],
            x1=22.3,
            y1=14.1419,
            x2=22.3,
            y2=30.8419,
            color_scheme=scheme,
            opacity=self.opacity,
        ))

        # paint2 - body kanan
        g.append(_valve_gradient(
            grad_id=ids['right'],
            x1=22.3915,
            y1=14.1419,
            x2=22.3915,
            y2=30.8419,
            color_scheme=scheme,
            opacity=self.opacity,
        ))

        # paint3 - handle manual atas
        g.append(_valve_gradient(
            grad_id=ids['handle'],
            x1=37.9958,
            y1=0,
            x2=37.9958,
            y2=3.79999,
            color_scheme=scheme,
            opacity=self.opacity,
        ))

    def render(self) -> draw.Group:
        transform_parts = [
            f'translate({self.x}, {self.y})'
        ]

        if self.rotation:
            transform_parts.append(
                f'rotate({self.rotation}, {self.WIDTH / 2}, {self.HEIGHT / 2})'
            )

        if self.scale != 1.0:
            transform_parts.append(f'scale({self.scale})')

        g = draw.Group(
            id=self.id,
            class_=f'equipment manual-valve {self.status}',
            transform=' '.join(transform_parts),
        )

        self._append_gradients(g)
        ids = self._gradient_ids()

        # Stem tengah
        g.append(draw.Path(
            d="M20.4256 2.32678H24.2256V22.5268H20.4256V2.32678Z",
            fill=f"url(  # {ids['stem']})",
        ))

        # Body kiri
        g.append(draw.Path(
            d="M1.90735e-05 14.1419V30.8419L22.3 22.5419L1.90735e-05 14.1419Z",
            fill=f"url(  # {ids['left']})",
        ))

        # Body kanan
        g.append(draw.Path(
            d="M44.6915 14.1419V30.8419L22.3915 22.5419L44.6915 14.1419Z",
            fill=f"url(  # {ids['right']})",
        ))

        # Handle manual atas
        g.append(draw.Path(
            d="M37.9958 3.79999V-1.21593e-05H6.69582V3.79999H37.9958Z",
            fill=f"url(  # {ids['handle']})",
        ))

        return g


# PUMP
class Pump(Equipment):
    WIDTH = 59
    HEIGHT = 54

    def __init__(
        self,
        id: str,
        x: float = 0,
        y: float = 0,
        status: str = 'normal',
        indicator_color: str | None = None,
        opacity: float = 1.0,
        indicator_opacity: float = 0.8,
        scale: float = 1.0,
        rotation: float = 0.0,
    ):
        super().__init__(
            id=id,
            x=x,
            y=y,
            status=status,
            ports={
                # Port umum untuk koneksi pipa
                'inlet': Port(0.125, 24.5687),
                'outlet': Port(58.7463, 10.95),

                # Optional reference ports
                'center': Port(24.025, 24.5687),
                'bottom-left': Port(10.3165, 53.2743),
                'bottom-right': Port(36.5026, 53.2743),
            },
        )

        self.indicator_color = indicator_color or _pump_indicator_color(status)
        self.opacity = opacity
        self.indicator_opacity = indicator_opacity
        self.scale = scale
        self.rotation = rotation

    def _grad_id(self, index: int) -> str:
        return f'{self.id}-gradient-{index}'

    def _append_gradients(self, g: draw.Group) -> None:
        """
        Gradient sesuai SVG pump.
        Semua id dibuat unik agar aman untuk banyak pump.
        """

        gradient_specs = [
            # paint0
            (0, 40.9167, 41.0501, 28.4167, 41.0501),

            # paint1
            (1, 43.1026, 50.2743, 29.9026, 50.2743),

            # paint2
            (2, 5.90231, 41.0501, 18.4023, 41.0501),

            # paint3
            (3, 3.71649, 50.2743, 16.9165, 50.2743),

            # paint4
            (4, 55.9178, 20.7805, 55.9178, 0.780539),

            # paint5
            (5, 48.025, 48.3687, 48.025, 0.768707),

            # paint6
            (6, 58.7463, 21.9, 58.7463, 0.00000762939),

            # paint7
            (7, 56.8187, 21.8079, 56.8187, 0.107906),

            # paint8
            (8, 58.5858, 21.5509, 58.5858, 0.350906),

            # paint9
            (9, 45.7285, 46.1, 2.3285, 46.1),

            # paint10
            (10, 34.8081, 35.2633, 13.3081, 35.2633),

            # paint11
            (11, 33.7017, 34.1653, 14.4017, 34.1653),

            # paint12
            (12, 25.2489, 25.7775, 22.8489, 25.7775),

            # paint13
            (13, 26.2355, 26.7565, 21.8355, 26.7565),

            # paint14
            (14, 25.8243, 26.3484, 22.3243, 26.3484),
        ]

        for index, x1, y1, x2, y2 in gradient_specs:
            g.append(_metallic_gradient(
                grad_id=self._grad_id(index),
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                colors=PUMP_METAL_STOPS,
            ))

    def render(self) -> draw.Group:
        transform_parts = [
            f'translate({self.x}, {self.y})'
        ]

        if self.rotation:
            transform_parts.append(
                f'rotate({self.rotation}, {self.WIDTH / 2}, {self.HEIGHT / 2})'
            )

        if self.scale != 1.0:
            transform_parts.append(f'scale({self.scale})')

        g = draw.Group(
            id=self.id,
            class_=f'equipment pump {self.status}',
            transform=' '.join(transform_parts),
        )

        self._append_gradients(g)

        # =====================================================
        # Pump feet / base
        # =====================================================

        g.append(draw.Path(
            d="M37.3167 41.0501H28.4167L32.0167 50.2501H40.9167L37.3167 41.0501Z",
            fill=f"url(  # {self._grad_id(0)})",
        ))

        g.append(draw.Path(
            d="M42.8026 50.2743H30.2026C30.0026 50.2743 29.9026 50.3743 29.9026 50.5743V52.8743C29.9026 53.0743 30.0026 53.2743 30.2026 53.2743H42.8026C43.0026 53.2743 43.1026 53.0743 43.1026 52.8743V50.5743C43.1026 50.3743 43.0026 50.2743 42.8026 50.2743Z",
            fill=f"url(  # {self._grad_id(1)})",
        ))

        g.append(draw.Path(
            d="M9.50231 41.0501H18.4023L14.8023 50.2501H5.90231L9.50231 41.0501Z",
            fill=f"url(  # {self._grad_id(2)})",
        ))

        g.append(draw.Path(
            d="M4.01649 50.2743H16.6165C16.8165 50.2743 16.9165 50.3743 16.9165 50.5743V52.8743C16.9165 53.0743 16.8165 53.2743 16.6165 53.2743H4.01649C3.81649 53.2743 3.71649 53.0743 3.71649 52.8743V50.5743C3.71649 50.3743 3.81649 50.2743 4.01649 50.2743Z",
            fill=f"url(  # {self._grad_id(3)})",
        ))

        # =====================================================
        # Outlet housing kanan atas
        # =====================================================

        g.append(draw.Path(
            d="M55.9178 20.7805V0.780539H24.0178V20.7805H55.9178Z",
            fill=f"url(  # {self._grad_id(4)})",
        ))

        # =====================================================
        # Main pump casing
        # =====================================================

        g.append(draw.Path(
            d="M24.025 48.3687C37.325 48.3687 48.025 37.6687 48.025 24.5687C48.025 11.4687 37.325 0.768707 24.025 0.768707C10.825 0.768707 0.124992 11.4687 0.124992 24.5687C0.124992 37.6687 10.825 48.3687 24.025 48.3687Z",
            fill=f"url(  # {self._grad_id(5)})",
            stroke="  # D4D6DB",
            stroke_width=0.25,
        ))

        # =====================================================
        # Outlet nozzle detail
        # =====================================================

        g.append(draw.Path(
            d="M58.7463 21.2V0.700006C58.7463 0.300007 58.1463 7.62939e-06 57.3463 7.62939e-06C56.5463 7.62939e-06 55.9463 0.300007 55.9463 0.700006V21.2C55.9463 21.6 56.5463 21.9 57.3463 21.9C58.1463 21.9 58.7463 21.6 58.7463 21.2Z",
            fill=f"url(  # {self._grad_id(6)})",
        ))

        g.append(draw.Path(
            d="M56.8187 0.107906C56.3187 0.107906 55.9187 0.407907 55.9187 0.807907V21.1079C55.9187 21.5079 56.3187 21.8079 56.8187 21.8079V0.107906Z",
            fill=f"url(  # {self._grad_id(7)})",
        ))

        g.append(draw.Path(
            d="M58.5858 21.2509V0.650908C58.5858 0.550907 58.4858 0.350906 58.2858 0.350906C58.1858 0.350906 58.0858 0.550907 58.0858 0.650908V21.2509C58.0858 21.3509 58.1858 21.5509 58.2858 21.5509C58.4858 21.5509 58.5858 21.3509 58.5858 21.2509Z",
            fill=f"url(  # {self._grad_id(8)})",
        ))

        # =====================================================
        # Inner casing rings
        # =====================================================

        g.append(draw.Path(
            d="M45.7285 24.6C45.7285 36.5 36.0285 46.1 24.0285 46.1C12.1285 46.1 2.3285 36.5 2.3285 24.6C2.3285 12.7 12.1285 3.10001 24.0285 3.10001C36.0285 3.10001 45.7285 12.7 45.7285 24.6Z",
            fill=f"url(  # {self._grad_id(9)})",
        ))

        g.append(draw.Path(
            d="M34.8081 24.5633C34.8081 30.4633 30.0081 35.2633 24.0081 35.2633C18.1081 35.2633 13.3081 30.4633 13.3081 24.5633C13.3081 18.6633 18.1081 13.9633 24.0081 13.9633C30.0081 13.9633 34.8081 18.6633 34.8081 24.5633Z",
            fill=f"url(  # {self._grad_id(10)})",
            stroke="  # 787F87",
        ))

        g.append(draw.Path(
            d="M33.7017 24.5653C33.7017 29.8653 29.4017 34.1653 24.1017 34.1653C18.7017 34.1653 14.4017 29.8653 14.4017 24.5653C14.4017 19.2653 18.7017 14.9653 24.1017 14.9653C29.4017 14.9653 33.7017 19.2653 33.7017 24.5653Z",
            fill=f"url(  # {self._grad_id(11)})",
        ))

        g.append(draw.Path(
            d="M25.2489 24.5775C25.2489 25.2775 24.7489 25.7775 24.0489 25.7775C23.3489 25.7775 22.8489 25.2775 22.8489 24.5775C22.8489 23.9775 23.3489 23.3775 24.0489 23.3775C24.7489 23.3775 25.2489 23.9775 25.2489 24.5775Z",
            fill=f"url(  # {self._grad_id(12)})",
        ))

        # =====================================================
        # Pump impeller / running indicator
        # Warnanya bisa berubah berdasarkan status
        # =====================================================

        g.append(draw.Path(
            d="M23.8753 14.9814H24.1753C24.3753 14.9814 24.4753 15.0814 24.4753 15.2814V33.8814C24.4753 34.0814 24.3753 34.1814 24.1753 34.1814H23.8753C23.6753 34.1814 23.5753 34.0814 23.5753 33.8814V15.2814C23.5753 15.0814 23.6753 14.9814 23.8753 14.9814Z",
            fill=self.indicator_color,
            fill_opacity=self.indicator_opacity,
        ))

        g.append(draw.Path(
            d="M32.3254 19.6071L32.4754 19.8669C32.5754 20.0401 32.5388 20.1767 32.3656 20.2767L16.171 29.6267C15.9978 29.7267 15.8611 29.6901 15.7611 29.5169L15.6111 29.2571C15.5111 29.0838 15.5478 28.9472 15.721 28.8472L31.9156 19.4972C32.0888 19.3972 32.2254 19.4338 32.3254 19.6071Z",
            fill=self.indicator_color,
            fill_opacity=self.indicator_opacity,
        ))

        g.append(draw.Path(
            d="M15.7627 19.608L15.6127 19.8678C15.5127 20.041 15.5493 20.1776 15.7225 20.2776L31.9171 29.6276C32.0904 29.7276 32.227 29.691 32.327 29.5178L32.477 29.258C32.577 29.0847 32.5404 28.9481 32.3671 28.8481L16.1725 19.4981C15.9993 19.3981 15.8627 19.4347 15.7627 19.608Z",
            fill=self.indicator_color,
            fill_opacity=self.indicator_opacity,
        ))

        # =====================================================
        # Center hub
        # =====================================================

        g.append(draw.Path(
            d="M26.2355 24.5565C26.2355 25.7565 25.2355 26.7565 24.0355 26.7565C22.8355 26.7565 21.8355 25.7565 21.8355 24.5565C21.8355 23.3565 22.8355 22.4565 24.0355 22.4565C25.2355 22.4565 26.2355 23.3565 26.2355 24.5565Z",
            fill=f"url(  # {self._grad_id(13)})",
        ))

        g.append(draw.Path(
            d="M25.8243 24.5484C25.8243 25.5484 25.0243 26.3484 24.0243 26.3484C23.0243 26.3484 22.3243 25.5484 22.3243 24.5484C22.3243 23.6484 23.0243 22.8484 24.0243 22.8484C25.0243 22.8484 25.8243 23.6484 25.8243 24.5484Z",
            fill=f"url(  # {self._grad_id(14)})",
        ))

        return g


# =========================================================
# INPUT / OUTPUT ARROW EQUIPMENT
# =========================================================

class InputOutputArrow(Equipment):
    """
    Arrow label untuk input/output process.

    Default mengikuti SVG:
    width=113 height=30
    path:
    M0 0H87.9L112.9 14.8L87.9 29.5H0L25 14.8L0 0Z
    """

    DEFAULT_WIDTH = 113
    DEFAULT_HEIGHT = 30

    def __init__(
        self,
        id: str,
        x: float = 0,
        y: float = 0,
        status: str = 'default',
        color_scheme: str | None = None,
        color: str | None = None,
        opacity: float = 1.0,
        width: float = DEFAULT_WIDTH,
        height: float = DEFAULT_HEIGHT,
        scale: float = 1.0,
        rotation: float = 0.0,
        flip: bool = False,
        stroke: str | None = None,
        stroke_width: float = 0.0,
    ):
        super().__init__(
            id=id,
            x=x,
            y=y,
            status=status,
            ports={
                # Port koneksi kiri-kanan
                'left': Port(26, height / 2),
                'right': Port(width, height / 2),
                'center': Port(width / 2, height / 2),
            },
        )

        self.color_scheme = color_scheme or status
        self.color = color or _io_arrow_color(self.color_scheme)
        self.opacity = opacity
        self.width = width
        self.height = height
        self.scale = scale
        self.rotation = rotation
        self.flip = flip
        self.stroke = stroke
        self.stroke_width = stroke_width

    @property
    def _sx(self) -> float:
        return self.width / 113.0

    @property
    def _sy(self) -> float:
        return self.height / 30.0

    def _x(self, value: float) -> float:
        return value * self._sx

    def _y(self, value: float) -> float:
        return value * self._sy

    def _path_d(self) -> str:
        """
        Path diskalakan dari reference SVG 113x30.

        SVG asli:
        M0 0
        H87.9
        L112.9 14.8
        L87.9 29.5
        H0
        L25 14.8
        L0 0
        Z
        """

        return (
            f"M{self._x(0)} {self._y(0)} "
            f"H{self._x(87.9)} "
            f"L{self._x(112.9)} {self._y(14.8)} "
            f"L{self._x(87.9)} {self._y(29.5)} "
            f"H{self._x(0)} "
            f"L{self._x(25)} {self._y(14.8)} "
            f"L{self._x(0)} {self._y(0)} "
            f"Z"
        )

    def render(self) -> draw.Group:
        transform_parts = [
            f'translate({self.x}, {self.y})'
        ]

        if self.rotation:
            transform_parts.append(
                f'rotate({self.rotation}, {self.width / 2}, {self.height / 2})'
            )

        if self.flip:
            # Flip horizontal di sekitar width arrow
            transform_parts.append(
                f'translate({self.width}, 0) scale(-1, 1)'
            )

        if self.scale != 1.0:
            transform_parts.append(f'scale({self.scale})')

        g = draw.Group(
            id=self.id,
            class_=f'equipment input-output-arrow {self.status}',
            transform=' '.join(transform_parts),
        )

        path_args = {
            'd': self._path_d(),
            'fill': self.color,
            'fill_opacity': self.opacity,
        }

        if self.stroke is not None and self.stroke_width > 0:
            path_args['stroke'] = self.stroke
            path_args['stroke_width'] = self.stroke_width

        g.append(draw.Path(**path_args))

        return g


# =========================================================
# CONTROLLER DISPLAY
# =========================================================

class Controller(Equipment):
    """Instrument display with tag label top and live value with unit bottom."""

    # --- Deklarasi Atribut untuk Pylance ---
    # Ini memberi tahu Pylance bahwa atribut dari parent class/init pasti ada di self
    id: str
    x: float
    y: float
    status: str
    width: float
    height: float
    tag: str
    value: float | int | str
    unit: str
    value_color: str
    value_decimals: int

    # --- Class Constants ---
    DEFAULT_WIDTH = 121
    DEFAULT_HEIGHT = 55
    CORNER_R = 2.5

    VALUE_COLORS = {
        'normal': '  # 00B050',
        'green': '  # 00B050',
        'running': '  # 00B050',

        'warning': '  # FFC000',
        'yellow': '  # FFC000',

        'alarm': '  # FF0000',
        'error': '  # FF0000',
        'red': '  # FF0000',

        'off': '  # 8F8F8F',
        'stopped': '  # 8F8F8F',
        'gray': '  # 8F8F8F',

        'white': '  # FFFFFF',
        'blue': '  # 0070C0',
    }

    def __init__(
        self,
        id: str,
        x: float = 0,
        y: float = 0,
        width: float = DEFAULT_WIDTH,
        height: float = DEFAULT_HEIGHT,
        tag: str = 'FI-100',
        value: float | int | str = 42.20,
        unit: str = 'lb/min',
        value_color: str = 'green',
        value_decimals: int = 2,
        status: str = 'normal'
    ) -> None:
        self.width = width
        self.height = height

        super().__init__(
            id=id,
            x=x,
            y=y,
            status=status,
            ports={
                'left': Port(0, self.height / 2),
                'right': Port(self.width, self.height / 2),
                'top': Port(self.width / 2, 0),
                'bottom': Port(self.width / 2, self.height),
                'center': Port(self.width / 2, self.height / 2),
            },
        )

        self.tag = tag
        self.value = value
        self.unit = unit
        self.value_color = value_color
        self.value_decimals = value_decimals

    def _resolve_value_color(self) -> str:
        return self.VALUE_COLORS.get(self.value_color, self.value_color)

    def _format_value(self) -> str:
        if isinstance(self.value, float):
            value_text = f'{self.value:.{self.value_decimals}f}'
        else:
            value_text = str(self.value)

        if self.unit:
            return f'{value_text} {self.unit}'

        return value_text

    def _centered_text(
        self,
        text: str,
        font_size: float,
        x: float,
        y: float,
        fill: str,
        font_weight: str = 'normal',
        text_id: str | None = None,
    ) -> draw.Text:
        # Menentukan tipe dict secara eksplisit agar Pylance tidak komplain saat unpacking kwarqs
        attrs: dict[str, Any] = {
            'fill': fill,
            'font_family': 'Courier Prime, Courier, monospace',
            'font_weight': font_weight,
            'text_anchor': 'middle',
            'dominant_baseline': 'central',
        }

        if text_id:
            attrs['id'] = text_id

        return draw.Text(
            str(text),
            font_size,
            x,
            y,
            **attrs
        ) # type: ignore

    def render(self) -> draw.Group:
        g = draw.Group(
            id=self.id,
            class_=f'equipment controller status-{self.status}',
            transform=f'translate({self.x},{self.y})',
        )

        w = self.width
        h = self.height
        r = self.CORNER_R
        mid_y = h / 2

        # Top half
        top = draw.Path(
            fill='black',
            stroke='white',
            stroke_width=1,
        )

        top.M(0.5, mid_y)
        top.V(r + 0.5)
        top.A(r, r, 0, 0, 1, r + 0.5, 0.5)
        top.H(w - r - 0.5)
        top.A(r, r, 0, 0, 1, w - 0.5, r + 0.5)
        top.V(mid_y)
        top.H(0.5)
        top.Z()

        g.append(top)

        # Bottom half
        bot = draw.Path(
            fill='black',
            stroke='white',
            stroke_width=1,
        )

        bot.M(0.5, mid_y)
        bot.H(w - 0.5)
        bot.V(h - r - 0.5)
        bot.A(r, r, 0, 0, 1, w - r - 0.5, h - 0.5)
        bot.H(r + 0.5)
        bot.A(r, r, 0, 0, 1, 0.5, h - r - 0.5)
        bot.V(mid_y)
        bot.Z()

        g.append(bot)

        # Tag label
        g.append(self._centered_text(
            self.tag,
            font_size=16,
            x=w / 2,
            y=mid_y / 2,
            fill='white',
            font_weight='bold',
            text_id=f'{self.id}-tag',
        ))

        # Value + unit
        g.append(self._centered_text(
            self._format_value(),
            font_size=16,
            x=w / 2,
            y=mid_y + ((h - mid_y) / 2),
            fill=self._resolve_value_color(),
            font_weight='bold',
            text_id=f'{self.id}-value',
        ))

        return g


# =========================================================
# PROCESS / PIPE LINE
# =========================================================

# PIPELINE LINES
class LineLine:
    """Polyline between waypoints with optional elbow radius or smooth curve."""

    def __init__(self, id: str,
                 waypoints: list[tuple[float, float]],
                 color: str = '  # 686E75',
                 width: float = 4,
                 mode: str = 'straight',
                 elbow_radius: float = 10,
                 status: str = 'normal'):
        self.id = id
        self.waypoints = waypoints
        self.color = color
        self.width = width
        self.mode = mode
        self.elbow_radius = elbow_radius
        self.status = status

    @staticmethod
    def from_ports(id: str, source: Equipment, source_port: str,
                   target: Equipment, target_port: str,
                   mid_points: list[tuple[float, float]] | None = None,
                   **kwargs) -> 'LineLine':
        sp = source.port_abs(source_port)
        tp = target.port_abs(target_port)
        pts: list[tuple[float, float]] = [(sp.x, sp.y)]
        if mid_points:
            pts.extend(mid_points)
        pts.append((tp.x, tp.y))
        return LineLine(id=id, waypoints=pts, **kwargs)

    def _build_path(self) -> draw.Path:
        p = draw.Path(
            fill='none',
            stroke=self.color,
            stroke_width=self.width,
            stroke_linecap='round',
            stroke_linejoin='round',
        )
        pts = self.waypoints
        if len(pts) < 2:
            return p

        if self.mode == 'curve':
            self._build_curve(p, pts)
        elif self.mode == 'elbow':
            self._build_elbow(p, pts)
        else:
            self._build_straight(p, pts)
        return p

    def _build_straight(self, p: draw.Path,
                        pts: list[tuple[float, float]]):
        p.M(*pts[0])
        for pt in pts[1:]:
            p.L(*pt)

    def _build_elbow(self, p: draw.Path,
                     pts: list[tuple[float, float]]):
        """Orthogonal segments with rounded corners at bends."""
        r = self.elbow_radius
        p.M(*pts[0])

        for i in range(1, len(pts) - 1):
            prev = pts[i - 1]
            curr = pts[i]
            nxt = pts[i + 1]

            dx_in = curr[0] - prev[0]
            dy_in = curr[1] - prev[1]
            dx_out = nxt[0] - curr[0]
            dy_out = nxt[1] - curr[1]

            len_in = (dx_in ** 2 + dy_in ** 2) ** 0.5
            len_out = (dx_out ** 2 + dy_out ** 2) ** 0.5

            if len_in == 0 or len_out == 0:
                p.L(*curr)
                continue

            actual_r = min(r, len_in / 2, len_out / 2)

            arc_sx = curr[0] - actual_r * dx_in / len_in
            arc_sy = curr[1] - actual_r * dy_in / len_in

            arc_ex = curr[0] + actual_r * dx_out / len_out
            arc_ey = curr[1] + actual_r * dy_out / len_out

            cross = dx_in * dy_out - dy_in * dx_out
            sweep = 1 if cross > 0 else 0

            p.L(arc_sx, arc_sy)
            p.A(actual_r, actual_r, 0, 0, sweep, arc_ex, arc_ey)

        p.L(*pts[-1])

    def _build_curve(self, p: draw.Path,
                     pts: list[tuple[float, float]]):
        """Smooth cubic bezier using Catmull-Rom â†’ Bezier conversion."""
        p.M(*pts[0])

        if len(pts) == 2:
            p.L(*pts[1])
            return

        padded = [pts[0]] + list(pts) + [pts[-1]]

        for i in range(1, len(padded) - 2):
            p0 = padded[i - 1]
            p1 = padded[i]
            p2 = padded[i + 1]
            p3 = padded[i + 2]

            cp1x = p1[0] + (p2[0] - p0[0]) / 6
            cp1y = p1[1] + (p2[1] - p0[1]) / 6
            cp2x = p2[0] - (p3[0] - p1[0]) / 6
            cp2y = p2[1] - (p3[1] - p1[1]) / 6

            p.C(cp1x, cp1y, cp2x, cp2y, p2[0], p2[1])

    def render(self) -> draw.Group:
        g = draw.Group(id=self.id,
                       class_=f'pipeline status-{self.status}')
        g.append(self._build_path())
        return g


# ARROW LINE
class ArrowLine(LineLine):
    """Line with a triangular arrowhead at the end."""

    def __init__(self, id: str,
                 waypoints: list[tuple[float, float]],
                 color: str = '  # 686E75',
                 width: float = 4,
                 arrow_size: float = 5,
                 mode: str = 'straight',
                 elbow_radius: float = 10,
                 status: str = 'normal'):
        super().__init__(id=id, waypoints=waypoints,
                         color=color, width=width,
                         mode=mode, elbow_radius=elbow_radius,
                         status=status)
        self.arrow_size = arrow_size

    @staticmethod
    def from_ports(id: str, source: Equipment, source_port: str,
                   target: Equipment, target_port: str,
                   mid_points: list[tuple[float, float]] | None = None,
                   **kwargs) -> 'ArrowLine':
        sp = source.port_abs(source_port)
        tp = target.port_abs(target_port)
        pts: list[tuple[float, float]] = [(sp.x, sp.y)]
        if mid_points:
            pts.extend(mid_points)
        pts.append((tp.x, tp.y))
        return ArrowLine(id=id, waypoints=pts, **kwargs)

    def render(self) -> draw.Group:
        g = draw.Group(id=self.id,
                       class_=f'pipeline arrow-line status-{self.status}')
        s = self.arrow_size
        marker_id = f'marker-arrow-{self.id}'
        m = draw.Marker(0, 0, s, s, id=marker_id,
                        markerWidth=s, markerHeight=s,
                        refX=s, refY=s / 2,
                        orient='auto-start-reverse')
        m.append(draw.Path(d=f'M0,0 L{s},{s / 2} L0,{s} Z',
                           fill=self.color))
        g.append(m)

        path = self._build_path()
        path.args['marker-end'] = f'url(  # {marker_id})'
        g.append(path)
        return g


# DASH LINE
class DashLine(LineLine):
    """Dashed line."""

    def __init__(self, id: str,
                 waypoints: list[tuple[float, float]],
                 color: str = '  # 686E75',
                 width: float = 4,
                 dash: str = '12 6',
                 mode: str = 'straight',
                 elbow_radius: float = 10,
                 status: str = 'normal'):
        super().__init__(id=id, waypoints=waypoints,
                         color=color, width=width,
                         mode=mode, elbow_radius=elbow_radius,
                         status=status)
        self.dash = dash

    @staticmethod
    def from_ports(id: str, source: Equipment, source_port: str,
                   target: Equipment, target_port: str,
                   mid_points: list[tuple[float, float]] | None = None,
                   **kwargs) -> 'DashLine':
        sp = source.port_abs(source_port)
        tp = target.port_abs(target_port)
        pts: list[tuple[float, float]] = [(sp.x, sp.y)]
        if mid_points:
            pts.extend(mid_points)
        pts.append((tp.x, tp.y))
        return DashLine(id=id, waypoints=pts, **kwargs)

    def render(self) -> draw.Group:
        g = draw.Group(id=self.id,
                       class_=f'pipeline dash-line status-{self.status}')
        path = self._build_path()
        path.args['stroke-dasharray'] = self.dash
        g.append(path)
        return g


# DOT END LINE
class DotEndLine(LineLine):
    """Line with a circular dot at the endpoint and a dashed stroke."""

    def __init__(self, id: str,
                 waypoints: list[tuple[float, float]],
                 color: str = '  # 686E75',
                 width: float = 4,
                 dot_radius: float = 2,
                 mode: str = 'straight',
                 elbow_radius: float = 10,
                 status: str = 'normal'):
        super().__init__(id=id, waypoints=waypoints,
                         color=color, width=width,
                         mode=mode, elbow_radius=elbow_radius,
                         status=status)
        self.dot_radius = dot_radius

    @staticmethod
    def from_ports(id: str, source: Equipment, source_port: str,
                   target: Equipment, target_port: str,
                   mid_points: list[tuple[float, float]] | None = None,
                   **kwargs) -> 'DotEndLine':
        sp = source.port_abs(source_port)
        tp = target.port_abs(target_port)
        pts: list[tuple[float, float]] = [(sp.x, sp.y)]
        if mid_points:
            pts.extend(mid_points)
        pts.append((tp.x, tp.y))
        return DotEndLine(id=id, waypoints=pts, **kwargs)

    def render(self) -> draw.Group:
        g = draw.Group(id=self.id,
                       class_=f'pipeline dot-end-line status-{self.status}')
        r = self.dot_radius
        d = r * 2
        marker_id = f'marker-dot-{self.id}'
        m = draw.Marker(0, 0, d, d, id=marker_id,
                        markerWidth=d, markerHeight=d,
                        refX=r, refY=r,
                        orient='auto')
        m.append(draw.Circle(r, r, r, fill=self.color))
        g.append(m)

        path = self._build_path()
        path.args['marker-end'] = f'url(  # {marker_id})'
        g.append(path)
        return g


__all__ = [
    # Reactor equipment
    'ReactorBody',
    'ReactorFluidLayer',
    'ReactorJacket',
    'ReactorJacketFluidLayer',
    # Valves & pumps
    'Valve',
    'ManualValve',
    'Pump',
    # Arrows & controllers
    'InputOutputArrow',
    'Controller',
    # Pipeline primitives
    'LineLine',
    'ArrowLine',
    'DashLine',
    'DotEndLine',
    # Color schemes
    'REACTOR_BODY_STOPS',
    'REACTOR_JACKET_STOPS',
    'REACTOR_FLUID_STOPS',
    'VALVE_GRAY_STOPS',
    'VALVE_GREEN_STOPS',
    'VALVE_YELLOW_STOPS',
    'VALVE_RED_STOPS',
    'VALVE_COLOR_SCHEMES',
    'PUMP_METAL_STOPS',
    'PUMP_INDICATOR_COLORS',
    'IO_ARROW_COLORS',
    'PROCESS_LINE_COLORS',
]
