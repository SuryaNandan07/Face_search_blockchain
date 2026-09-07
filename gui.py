import os
import sys
import io
import time
import queue
import threading
import datetime
import webbrowser
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
from dotenv import load_dotenv

# Import unchanged backend functions
from blockchain.main import run_pipeline
from blockchain.write_record import connect_blockchain

load_dotenv()


# ============================================================================
# STDOUT / STDERR STREAM REDIRECTOR (THREAD-SAFE WITH CARRIAGE RETURN CLEANUP)
# ============================================================================

class StreamRedirector(io.TextIOBase):
    def __init__(self, msg_queue, original_stream):
        super().__init__()
        self.msg_queue = msg_queue
        self.original_stream = original_stream

    def write(self, text):
        if text:
            # Handle carriage returns cleanly so terminal output doesn't garble
            clean_text = text.replace("\r\n", "\n").replace("\r", "\n")
            self.msg_queue.put(clean_text)
            try:
                self.original_stream.write(text)
                self.original_stream.flush()
            except Exception:
                pass
        return len(text)

    def flush(self):
        try:
            self.original_stream.flush()
        except Exception:
            pass


# ============================================================================
# MAIN TKINTER GUI APPLICATION
# ============================================================================

class RetroFaceSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FACESEARCH.EXE — Visual Intelligence & Blockchain Verification")
        self.root.geometry("1380x900")
        self.root.minsize(1120, 760)
        self.root.configure(bg="#000000")

        # Application state
        self.selected_image_path = None
        self.image_dimensions = None
        self.input_photo_tk = None
        self.best_photo_tk = None
        self.cand_photos_tk = []
        self.log_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.is_searching = False
        self.anim_frame_idx = 0
        self.anim_timer_id = None

        # Check connection states
        self.serpapi_connected = bool(os.getenv("SERPAPI_KEY"))
        self.facenet_ready = True
        self.blockchain_connected = False

        # Palette derived from the reference image
        self.C_BG = "#050508"
        self.C_PANEL = "#0a0a0e"
        self.C_PANEL_HDR = "#120404"
        self.C_BORDER_RED = "#cc0000"
        self.C_BORDER_GREEN = "#00e676"
        self.C_BORDER_ORANGE = "#ff8c00"
        self.C_BORDER_MUTED = "#222232"
        
        self.C_TEXT = "#e6e6e6"
        self.C_TEXT_MUTED = "#888899"
        self.C_CYAN = "#00d2ff"
        self.C_RED = "#ff0000"
        self.C_ORANGE = "#ff8c00"
        self.C_YELLOW = "#ffcc00"
        self.C_GOLD = "#ffd700"
        self.C_GREEN = "#00ff66"

        self._setup_styles()
        self._build_ui()

        # Start periodic queue & clock checker
        self.root.after(50, self._process_queues)
        self.root.after(1000, self._update_clock)

        # Initial blockchain check in background
        threading.Thread(target=self._check_initial_services, daemon=True).start()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TScrollbar", background="#1a1a24", troughcolor="#050508", bordercolor="#333344", arrowcolor="#ff0000")

    # =========================================================================
    # UI CONSTRUCTION
    # =========================================================================

    def _build_ui(self):
        # Outer application window border (Solid 2px Red Frame)
        self.outer_frame = tk.Frame(self.root, bg=self.C_BG, bd=2, relief=tk.SOLID, highlightbackground=self.C_BORDER_RED, highlightthickness=2)
        self.outer_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Top Bar (Hackathon tag & System Online only - File/Search/Tools removed)
        self._build_top_bar(self.outer_frame)

        # Main Header
        self._build_header(self.outer_frame)

        # Main grid container for panels
        self.main_grid = tk.Frame(self.outer_frame, bg=self.C_BG, padx=4, pady=4)
        self.main_grid.pack(fill=tk.BOTH, expand=True)

        # Configure Grid Layout (Row 0: Top Panels, Row 1: Bottom Panels)
        self.main_grid.rowconfigure(0, weight=6)
        self.main_grid.rowconfigure(1, weight=4)

        self.main_grid.columnconfigure(0, weight=3, minsize=320) # Input Panel
        self.main_grid.columnconfigure(1, weight=4, minsize=420) # Terminal Panel
        self.main_grid.columnconfigure(2, weight=5, minsize=460) # Matches Panel

        # --- ROW 0: TOP PANELS ---
        self._build_input_panel(self.main_grid, row=0, col=0)
        self._build_terminal_panel(self.main_grid, row=0, col=1)
        self._build_results_panel(self.main_grid, row=0, col=2)

        # --- ROW 1: BOTTOM PANELS ---
        # Blockchain verification extended to span cols 0 & 1 for maximum visibility
        self._build_blockchain_panel(self.main_grid, row=1, col=0, columnspan=2)
        # Search Statistics in col 2 (About removed as requested)
        self._build_statistics_panel(self.main_grid, row=1, col=2)

        # Bottom Status Bar
        self._build_status_bar(self.outer_frame)

    # -------------------------------------------------------------------------
    # TOP SYSTEM BAR (Cleaned up: File/Tools removed)
    # -------------------------------------------------------------------------
    def _build_top_bar(self, parent):
        top_bar = tk.Frame(parent, bg="#050508", bd=1, relief=tk.SOLID, highlightbackground=self.C_BORDER_RED, highlightthickness=1)
        top_bar.pack(fill=tk.X, side=tk.TOP, pady=(0, 2))

        left_tag = tk.Label(
            top_bar,
            text="FACESEARCH.EXE  |  VISUAL INTELLIGENCE WORKSTATION",
            font=("Consolas", 8, "bold"),
            fg=self.C_CYAN,
            bg="#050508",
            padx=10,
            pady=3,
        )
        left_tag.pack(side=tk.LEFT)

        self.lbl_sys_online = tk.Label(
            top_bar,
            text="HH GOA HACKATHON 2026    ● SYSTEM ONLINE",
            font=("Consolas", 8, "bold"),
            fg=self.C_GREEN,
            bg="#050508",
            padx=10,
        )
        self.lbl_sys_online.pack(side=tk.RIGHT)

    # -------------------------------------------------------------------------
    # MAIN HEADER
    # -------------------------------------------------------------------------
    def _build_header(self, parent):
        header_frame = tk.Frame(parent, bg=self.C_PANEL, bd=1, relief=tk.SOLID, highlightbackground=self.C_BORDER_RED, highlightthickness=1)
        header_frame.pack(fill=tk.X, side=tk.TOP, pady=(0, 4))

        # Left title section
        title_box = tk.Frame(header_frame, bg=self.C_PANEL, padx=12, pady=6)
        title_box.pack(side=tk.LEFT, fill=tk.Y)

        lbl_main_title = tk.Label(
            title_box,
            text="FACESEARCH.EXE",
            font=("Consolas", 24, "bold"),
            fg=self.C_RED,
            bg=self.C_PANEL,
        )
        lbl_main_title.pack(anchor="w")

        lbl_tagline = tk.Label(
            title_box,
            text="FIND   •   VERIFY   •   PREVENT",
            font=("Consolas", 9, "bold"),
            fg=self.C_ORANGE,
            bg=self.C_PANEL,
        )
        lbl_tagline.pack(anchor="w")

        # Middle subtitle
        mid_box = tk.Frame(header_frame, bg=self.C_PANEL, padx=10, pady=6)
        mid_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        lbl_sub_title = tk.Label(
            mid_box,
            text="- REAL-WORLD VISUAL SEARCH\n  POWERED BY AI + BLOCKCHAIN",
            font=("Consolas", 10, "bold"),
            fg="#ffffff",
            bg=self.C_PANEL,
            justify=tk.LEFT,
        )
        lbl_sub_title.pack(anchor="w", pady=6)

        # Right quote frame (Red Bordered Box)
        right_box = tk.Frame(header_frame, bg=self.C_PANEL, padx=12, pady=6)
        right_box.pack(side=tk.RIGHT, fill=tk.Y)

        quote_frame = tk.Frame(right_box, bg="#08080c", bd=1, relief=tk.SOLID, highlightbackground=self.C_BORDER_RED, highlightthickness=1, padx=12, pady=6)
        quote_frame.pack(anchor="e")

        lbl_quote = tk.Label(
            quote_frame,
            text='"A SAFER INTERNET\nTHROUGH VISUAL INTELLIGENCE"',
            font=("Consolas", 8, "italic", "bold"),
            fg=self.C_YELLOW,
            bg="#08080c",
            justify=tk.CENTER,
        )
        lbl_quote.pack()

    # -------------------------------------------------------------------------
    # 1. INPUT IMAGE PANEL (Row 0, Col 0)
    # -------------------------------------------------------------------------
    def _build_input_panel(self, parent, row, col):
        panel = self._create_panel_frame(parent, "1. INPUT IMAGE", icon="👤", header_color=self.C_RED, border_color=self.C_BORDER_RED)
        panel.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        content = tk.Frame(panel, bg=self.C_PANEL, padx=8, pady=6)
        content.pack(fill=tk.BOTH, expand=True)

        # Image preview frame
        preview_box = tk.Frame(content, bg="#000000", bd=1, relief=tk.SOLID, highlightbackground=self.C_BORDER_RED, highlightthickness=1, height=180)
        preview_box.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self.lbl_input_img = tk.Label(
            preview_box,
            text="DROP IMAGE HERE\nor choose an image",
            font=("Consolas", 8, "bold"),
            fg=self.C_TEXT_MUTED,
            bg="#000000",
            justify=tk.CENTER,
        )
        self.lbl_input_img.pack(fill=tk.BOTH, expand=True)

        # Filename input box with X clear button
        fn_frame = tk.Frame(content, bg="#000000", bd=1, relief=tk.SOLID, highlightbackground="#333333", highlightthickness=1)
        fn_frame.pack(fill=tk.X, pady=(0, 4))

        self.lbl_filename = tk.Label(
            fn_frame,
            text="no_image_selected.jpg",
            font=("Consolas", 9),
            fg=self.C_TEXT_MUTED,
            bg="#000000",
            anchor="w",
            padx=6,
            pady=3,
        )
        self.lbl_filename.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_clear_img = tk.Button(
            fn_frame,
            text="✕",
            font=("Consolas", 9, "bold"),
            fg=self.C_RED,
            bg="#000000",
            bd=0,
            activebackground="#1a0000",
            activeforeground=self.C_RED,
            cursor="hand2",
            command=self._clear_selected_image,
        )
        btn_clear_img.pack(side=tk.RIGHT, padx=4)

        # Image dimensions row
        self.lbl_dimensions = tk.Label(
            content,
            text="Dimensions: N/A",
            font=("Consolas", 8),
            fg=self.C_TEXT_MUTED,
            bg=self.C_PANEL,
            anchor="w",
        )
        self.lbl_dimensions.pack(fill=tk.X, pady=(0, 4))

        # Buttons
        btn_choose = tk.Button(
            content,
            text="📂 Choose Image...",
            font=("Consolas", 9, "bold"),
            bg="#1a1a1a",
            fg="#ffffff",
            activebackground="#2a2a2a",
            activeforeground="#ffffff",
            bd=1,
            relief=tk.RAISED,
            cursor="hand2",
            pady=4,
            command=self._choose_image,
        )
        btn_choose.pack(fill=tk.X, pady=(0, 4))

        self.btn_start_search = tk.Button(
            content,
            text="▶ START SEARCH",
            font=("Consolas", 11, "bold"),
            bg="#cc0000",
            fg="#ffffff",
            activebackground="#990000",
            activeforeground="#ffffff",
            bd=1,
            relief=tk.RAISED,
            cursor="hand2",
            pady=6,
            state=tk.DISABLED,
            command=self._on_start_search_click,
        )
        self.btn_start_search.pack(fill=tk.X)

        lbl_fmt = tk.Label(
            content,
            text="Supported formats: JPG, PNG, WEBP",
            font=("Consolas", 8, "italic"),
            fg=self.C_TEXT_MUTED,
            bg=self.C_PANEL,
            anchor="w",
        )
        lbl_fmt.pack(anchor="w", pady=(3, 0))

    # -------------------------------------------------------------------------
    # 2. SYSTEM OUTPUT PANEL (Row 0, Col 1)
    # -------------------------------------------------------------------------
    def _build_terminal_panel(self, parent, row, col):
        panel = self._create_panel_frame(parent, "2. SYSTEM OUTPUT", icon="💻", header_color=self.C_RED, border_color=self.C_BORDER_RED)
        panel.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        # Clear button in header
        btn_clear_term = tk.Button(
            panel.header_box,
            text="Clear",
            font=("Consolas", 8, "bold"),
            bg="#1c1c1c",
            fg="#ffffff",
            activebackground="#333333",
            activeforeground="#ffffff",
            bd=1,
            relief=tk.RAISED,
            padx=8,
            pady=1,
            cursor="hand2",
            command=self._clear_terminal,
        )
        btn_clear_term.pack(side=tk.RIGHT, padx=6, pady=2)

        term_frame = tk.Frame(panel, bg="#040407", padx=4, pady=4)
        term_frame.pack(fill=tk.BOTH, expand=True)

        self.txt_terminal = tk.Text(
            term_frame,
            font=("Consolas", 9),
            bg="#040407",
            fg=self.C_CYAN,
            insertbackground=self.C_CYAN,
            selectbackground="#1a3344",
            selectforeground="#ffffff",
            bd=0,
            wrap=tk.WORD,
            padx=6,
            pady=6,
        )

        scrollbar = ttk.Scrollbar(term_frame, orient=tk.VERTICAL, command=self.txt_terminal.yview)
        self.txt_terminal.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt_terminal.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Initial timestamped log message
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._append_terminal_text(f"[{ts}] Initializing Face Search + Blockchain System...\n")

    # -------------------------------------------------------------------------
    # 3. SEARCH MATCHES PANEL (Row 0, Col 2 - SHOWS ALL MATCHES + BEST HIGHLIGHT)
    # -------------------------------------------------------------------------
    def _build_results_panel(self, parent, row, col):
        panel = self._create_panel_frame(parent, "3. SEARCH MATCHES", icon="🎯", header_color=self.C_ORANGE, border_color=self.C_BORDER_RED)
        panel.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        self.results_container = tk.Frame(panel, bg=self.C_PANEL, padx=6, pady=6)
        self.results_container.pack(fill=tk.BOTH, expand=True)

        # Placeholder message
        self.lbl_results_placeholder = tk.Label(
            self.results_container,
            text="[ NO SEARCH EXECUTION YET ]\nReal results from Google Lens, FaceNet512 & Blockchain\nwill be presented here after search completes.",
            font=("Consolas", 9, "italic"),
            fg=self.C_TEXT_MUTED,
            bg=self.C_PANEL,
            pady=40,
        )
        self.lbl_results_placeholder.pack(fill=tk.BOTH, expand=True)

    # -------------------------------------------------------------------------
    # 4. BLOCKCHAIN VERIFICATION PANEL (Row 1, Col 0-1 EXTENDED)
    # -------------------------------------------------------------------------
    def _build_blockchain_panel(self, parent, row, col, columnspan=2):
        self.bc_panel_frame = self._create_panel_frame(parent, "4. BLOCKCHAIN VERIFICATION", icon="🧊", header_color=self.C_GREEN, border_color=self.C_BORDER_GREEN)
        self.bc_panel_frame.grid(row=row, column=col, columnspan=columnspan, sticky="nsew", padx=2, pady=2)

        content = tk.Frame(self.bc_panel_frame, bg=self.C_PANEL, padx=10, pady=8)
        content.pack(fill=tk.BOTH, expand=True)

        # Dynamic Blockchain Canvas Flow Diagram (Extended width)
        self.bc_canvas = tk.Canvas(content, bg="#040407", height=42, highlightthickness=1, highlightbackground="#222233")
        self.bc_canvas.pack(fill=tk.X, pady=(0, 6))

        # Data fields & checkmarks split
        fields_frame = tk.Frame(content, bg=self.C_PANEL)
        fields_frame.pack(fill=tk.X)

        fields_left = tk.Frame(fields_frame, bg=self.C_PANEL)
        fields_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lbl_tx_hash = self._create_key_val_row(fields_left, "Transaction Hash :", "Waiting for execution...")
        self.lbl_fingerprint = self._create_key_val_row(fields_left, "Fingerprint      :", "Waiting for execution...")
        self.lbl_block_num = self._create_key_val_row(fields_left, "Block Number     :", "-")

        # Right-side status checkmarks (3 Honest States)
        fields_right = tk.Frame(fields_frame, bg=self.C_PANEL, padx=8)
        fields_right.pack(side=tk.RIGHT, anchor="n")

        self.lbl_ind_stored = tk.Label(fields_right, text="✓ Record stored", font=("Consolas", 9, "bold"), fg=self.C_GREEN, bg=self.C_PANEL, anchor="w")
        self.lbl_ind_stored.pack(anchor="w")

        self.lbl_ind_retrieved = tk.Label(fields_right, text="✓ Record retrieved", font=("Consolas", 9, "bold"), fg=self.C_GREEN, bg=self.C_PANEL, anchor="w")
        self.lbl_ind_retrieved.pack(anchor="w")

        self.lbl_ind_match = tk.Label(fields_right, text="✓ Fingerprint match", font=("Consolas", 9, "bold"), fg=self.C_GREEN, bg=self.C_PANEL, anchor="w")
        self.lbl_ind_match.pack(anchor="w")

        # Prominent Result Status Banner
        self.bc_banner = tk.Frame(content, bg="#003311", bd=1, relief=tk.SOLID, highlightbackground=self.C_BORDER_GREEN, highlightthickness=1, pady=6)
        self.bc_banner.pack(fill=tk.X, pady=(6, 0))

        self.lbl_bc_status = tk.Label(
            self.bc_banner,
            text="✓ VERIFICATION SUCCESSFUL",
            font=("Consolas", 11, "bold"),
            fg="#ffffff",
            bg="#003311",
        )
        self.lbl_bc_status.pack()

        self._draw_blockchain_diagram(state="IDLE")

    def _draw_blockchain_diagram(self, state="IDLE", block_num=1):
        self.bc_canvas.delete("all")
        w = self.bc_canvas.winfo_width()
        if w < 100:
            w = 600
        h = 42

        if state == "SUCCESS":
            color = self.C_GREEN
            nodes = [("FINGERPRINT", 70), ("[ HASH GENERATED ]", 210), (f"[ BLOCK #{block_num} ]", 370), ("✓ VERIFIED", 510), ("🔒 LOCK", 630)]
        elif state == "OFFLINE":
            color = self.C_RED
            nodes = [("FINGERPRINT", 90), ("[ LOCAL HASH ]", 270), ("✕ GANACHE OFFLINE", 480)]
        elif state == "RUNNING":
            color = self.C_ORANGE
            nodes = [("FINGERPRINT", 70), ("[ HASH ]", 210), ("[ SUBMITTING ]", 370), ("🔒 PENDING", 530)]
        elif state == "FAILED":
            color = self.C_RED
            nodes = [("FINGERPRINT", 70), ("[ HASH ]", 210), ("✕ FAILED", 350)]
        else: # IDLE
            color = self.C_TEXT_MUTED
            nodes = [("FINGERPRINT", 70), ("[ HASH GENERATION ]", 230), ("[ BLOCKCHAIN WRITE ]", 410), ("🔒 LOCK", 570)]

        for i in range(len(nodes) - 1):
            x1 = nodes[i][1] + 45
            x2 = nodes[i + 1][1] - 45
            self.bc_canvas.create_line(x1, h // 2, x2, h // 2, fill=color, dash=(4, 2) if state == "RUNNING" else None, width=1)

        for label, x in nodes:
            bx1, by1 = x - 50, h // 2 - 12
            bx2, by2 = x + 50, h // 2 + 12
            self.bc_canvas.create_rectangle(bx1, by1, bx2, by2, outline=color, fill="#000000", width=1)
            self.bc_canvas.create_text(x, h // 2, text=label, fill=color, font=("Consolas", 8, "bold"))

    # -------------------------------------------------------------------------
    # 5. SEARCH STATISTICS PANEL (Row 1, Col 2 - COMPACT)
    # -------------------------------------------------------------------------
    def _build_statistics_panel(self, parent, row, col):
        stats_panel = self._create_panel_frame(parent, "5. SEARCH STATISTICS", icon="📊", header_color=self.C_ORANGE, border_color=self.C_BORDER_RED)
        stats_panel.grid(row=row, column=col, sticky="nsew", padx=2, pady=2)

        s_content = tk.Frame(stats_panel, bg=self.C_PANEL, padx=8, pady=6)
        s_content.pack(fill=tk.BOTH, expand=True)

        self.lbl_stat_cand = self._create_key_val_row(s_content, "Candidates Received :", "0")
        self.lbl_stat_fetched = self._create_key_val_row(s_content, "Images Fetched      :", "0")
        self.lbl_stat_unavail = self._create_key_val_row(s_content, "Images Unavailable  :", "0")
        self.lbl_stat_time = self._create_key_val_row(s_content, "Search Time        :", "0.00s")

    # -------------------------------------------------------------------------
    # 7. STATUS BAR
    # -------------------------------------------------------------------------
    def _build_status_bar(self, parent):
        status_frame = tk.Frame(parent, bg="#050508", bd=1, relief=tk.SOLID, highlightbackground=self.C_BORDER_RED, highlightthickness=1)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(4, 0))

        # Status text
        self.lbl_app_status = tk.Label(
            status_frame,
            text="Ready.",
            font=("Consolas", 9, "bold"),
            fg=self.C_YELLOW,
            bg="#050508",
            padx=8,
            pady=3,
        )
        self.lbl_app_status.pack(side=tk.LEFT)

        tk.Label(status_frame, text="|", fg="#333333", bg="#050508").pack(side=tk.LEFT, padx=4)

        # Service indicators
        self.lbl_ind_serp = tk.Label(
            status_frame,
            text="● SerpApi Connected" if self.serpapi_connected else "● SerpApi Key Missing",
            font=("Consolas", 8, "bold"),
            fg=self.C_GREEN if self.serpapi_connected else self.C_RED,
            bg="#050508",
        )
        self.lbl_ind_serp.pack(side=tk.LEFT, padx=6)

        self.lbl_ind_face = tk.Label(
            status_frame,
            text="● FaceNet512 Ready",
            font=("Consolas", 8, "bold"),
            fg=self.C_GREEN,
            bg="#050508",
        )
        self.lbl_ind_face.pack(side=tk.LEFT, padx=6)

        self.lbl_ind_bc = tk.Label(
            status_frame,
            text="● Checking Blockchain...",
            font=("Consolas", 8, "bold"),
            fg=self.C_YELLOW,
            bg="#050508",
        )
        self.lbl_ind_bc.pack(side=tk.LEFT, padx=6)

        # Real-time Clock
        self.lbl_clock = tk.Label(
            status_frame,
            text="📅 09/06/2026 10:24:15 AM",
            font=("Consolas", 8),
            fg=self.C_YELLOW,
            bg="#050508",
            padx=8,
        )
        self.lbl_clock.pack(side=tk.RIGHT)

    # =========================================================================
    # HELPERS & UTILITIES
    # =========================================================================

    def _create_panel_frame(self, parent, title, icon=None, header_color=None, border_color=None):
        if border_color is None:
            border_color = self.C_BORDER_RED
        if header_color is None:
            header_color = self.C_RED

        panel = tk.Frame(parent, bg=self.C_PANEL, bd=1, relief=tk.SOLID, highlightbackground=border_color, highlightthickness=1)

        header_box = tk.Frame(panel, bg=self.C_PANEL_HDR, padx=6, pady=3)
        header_box.pack(fill=tk.X, side=tk.TOP)
        panel.header_box = header_box

        # Icon box
        if icon:
            icon_lbl = tk.Label(header_box, text=icon, font=("Consolas", 9, "bold"), fg="#ffffff", bg=header_color, padx=4, pady=1)
            icon_lbl.pack(side=tk.LEFT, padx=(0, 6))

        lbl = tk.Label(
            header_box,
            text=title,
            font=("Consolas", 9, "bold"),
            fg=header_color,
            bg=self.C_PANEL_HDR,
        )
        lbl.pack(side=tk.LEFT)

        return panel

    def _create_key_val_row(self, parent, label_text, default_val):
        row = tk.Frame(parent, bg=self.C_PANEL)
        row.pack(fill=tk.X, pady=1)

        lbl_k = tk.Label(row, text=label_text, font=("Consolas", 8), fg=self.C_TEXT_MUTED, bg=self.C_PANEL, width=18, anchor="w")
        lbl_k.pack(side=tk.LEFT)

        lbl_v = tk.Label(row, text=default_val, font=("Consolas", 8, "bold"), fg=self.C_TEXT, bg=self.C_PANEL, anchor="w")
        lbl_v.pack(side=tk.LEFT, fill=tk.X, expand=True)

        return lbl_v

    def _update_clock(self):
        now_str = datetime.datetime.now().strftime("📅 %m/%d/%Y   %I:%M:%S %p")
        self.lbl_clock.config(text=now_str)
        self.root.after(1000, self._update_clock)

    def _check_initial_services(self):
        w3 = connect_blockchain()
        self.blockchain_connected = (w3 is not None)

        def update_ui():
            if self.blockchain_connected:
                self.lbl_ind_bc.config(text="● Blockchain Node Connected", fg=self.C_GREEN)
            else:
                self.lbl_ind_bc.config(text="● Blockchain Node Offline", fg=self.C_RED)

        self.root.after(0, update_ui)

    def _clear_terminal(self):
        self.txt_terminal.delete("1.0", tk.END)

    def _append_terminal_text(self, text):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if text.startswith("["):
            formatted = text
        else:
            formatted = f"[{ts}] {text}"
        
        self.txt_terminal.insert(tk.END, formatted)
        self.txt_terminal.see(tk.END)

    # =========================================================================
    # BUTTON LOADING ANIMATION
    # =========================================================================

    def _animate_search_button(self):
        if not self.is_searching:
            return

        frames = ["◐ SEARCHING...", "◓ SEARCHING...", "◑ SEARCHING...", "◒ SEARCHING..."]
        txt = frames[self.anim_frame_idx % len(frames)]
        self.anim_frame_idx += 1

        self.btn_start_search.config(text=txt, bg=self.C_ORANGE)
        self.anim_timer_id = self.root.after(150, self._animate_search_button)

    def _stop_search_button_animation(self, final_state="COMPLETE"):
        self.is_searching = False
        if self.anim_timer_id:
            self.root.after_cancel(self.anim_timer_id)
            self.anim_timer_id = None

        if final_state == "COMPLETE":
            self.btn_start_search.config(text="✓ SEARCH COMPLETE", bg="#00aa44", state=tk.NORMAL)
        elif final_state == "ERROR":
            self.btn_start_search.config(text="✕ SEARCH FAILED", bg="#cc0000", state=tk.NORMAL)
        else:
            self.btn_start_search.config(text="▶ START SEARCH", bg="#cc0000", state=tk.NORMAL)

    # =========================================================================
    # USER ACTIONS
    # =========================================================================

    def _choose_image(self):
        file_path = filedialog.askopenfilename(
            title="Select Input Image for Visual Search",
            filetypes=[
                ("Image Files", "*.jpg *.jpeg *.png *.webp"),
                ("JPEG Images", "*.jpg *.jpeg"),
                ("PNG Images", "*.png"),
                ("WebP Images", "*.webp"),
                ("All Files", "*.*"),
            ],
        )

        if not file_path:
            return

        self.selected_image_path = file_path
        filename = Path(file_path).name
        self.lbl_filename.config(text=filename, fg=self.C_CYAN)
        self.btn_start_search.config(text="▶ START SEARCH", bg="#cc0000", state=tk.NORMAL)

        # Show thumbnail preview keeping original aspect ratio & get dimensions
        try:
            img = Image.open(file_path)
            w, h = img.size
            self.image_dimensions = f"{w} x {h} px"
            self.lbl_dimensions.config(text=f"Dimensions: {self.image_dimensions}", fg=self.C_TEXT)

            img.thumbnail((148, 148))
            self.input_photo_tk = ImageTk.PhotoImage(img)
            self.lbl_input_img.config(image=self.input_photo_tk, text="")
        except Exception as e:
            self.lbl_input_img.config(image="", text=f"Preview Error:\n{e}")
            self.lbl_dimensions.config(text="Dimensions: Unknown", fg=self.C_TEXT_MUTED)

    def _clear_selected_image(self):
        self.selected_image_path = None
        self.image_dimensions = None
        self.input_photo_tk = None
        self.lbl_filename.config(text="no_image_selected.jpg", fg=self.C_TEXT_MUTED)
        self.lbl_dimensions.config(text="Dimensions: N/A", fg=self.C_TEXT_MUTED)
        self.lbl_input_img.config(image="", text="DROP IMAGE HERE\nor choose an image")
        self.btn_start_search.config(text="▶ START SEARCH", bg="#cc0000", state=tk.DISABLED)

    def _on_start_search_click(self):
        if not self.selected_image_path or self.is_searching:
            return

        # Start search state & loading animation
        self.is_searching = True
        self.anim_frame_idx = 0
        self.btn_start_search.config(state=tk.DISABLED)
        self._animate_search_button()

        self.lbl_app_status.config(text="Searching...", fg=self.C_ORANGE)
        self._clear_terminal()

        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._append_terminal_text(f"[{ts}] Starting pipeline execution for: {self.selected_image_path}\n")

        # Reset blockchain panel
        self.lbl_tx_hash.config(text="Processing...", fg=self.C_ORANGE)
        self.lbl_fingerprint.config(text="Generating...", fg=self.C_ORANGE)
        self.lbl_block_num.config(text="Pending...", fg=self.C_ORANGE)

        self.lbl_ind_stored.config(text="○ Record stored", fg=self.C_TEXT_MUTED)
        self.lbl_ind_retrieved.config(text="○ Record retrieved", fg=self.C_TEXT_MUTED)
        self.lbl_ind_match.config(text="○ Fingerprint match", fg=self.C_TEXT_MUTED)

        self.lbl_bc_status.config(text="PROCESSING BLOCKCHAIN PIPELINE...", fg=self.C_ORANGE, bg="#1a1408")
        self.bc_banner.config(highlightbackground=self.C_BORDER_ORANGE)
        self.bc_panel_frame.config(highlightbackground=self.C_BORDER_ORANGE)
        self._draw_blockchain_diagram(state="RUNNING")

        # Clear results panel placeholder
        for child in self.results_container.winfo_children():
            child.destroy()

        lbl_running = tk.Label(
            self.results_container,
            text="[ PIPELINE EXECUTING ]\nFetching Google Lens candidates, running FaceNet512 & pHash comparison...\nPlease watch SYSTEM OUTPUT panel for real-time progress.",
            font=("Consolas", 10, "bold"),
            fg=self.C_CYAN,
            bg=self.C_PANEL,
            pady=40,
        )
        lbl_running.pack(fill=tk.BOTH, expand=True)

        # Launch background search thread
        t = threading.Thread(target=self._run_pipeline_worker, args=(self.selected_image_path,), daemon=True)
        t.start()

    # =========================================================================
    # PIPELINE EXECUTION THREAD
    # =========================================================================

    def _run_pipeline_worker(self, image_path):
        start_time = time.time()

        # Redirect stdout/stderr to thread queue
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        redirector = StreamRedirector(self.log_queue, orig_stdout)

        sys.stdout = redirector
        sys.stderr = redirector

        try:
            res = run_pipeline(image_path)
            elapsed = time.time() - start_time
            self.result_queue.put(("SUCCESS", res, elapsed))
        except Exception as e:
            elapsed = time.time() - start_time
            self.result_queue.put(("ERROR", str(e), elapsed))
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr

    # =========================================================================
    # QUEUE & UPDATE PROCESSING
    # =========================================================================

    def _process_queues(self):
        # 1. Drain terminal log queue
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self._append_terminal_text(msg)
            except queue.Empty:
                break

        # 2. Check result queue
        while not self.result_queue.empty():
            try:
                status, payload, elapsed = self.result_queue.get_nowait()
                if status == "SUCCESS":
                    self._on_pipeline_success(payload, elapsed)
                else:
                    self._on_pipeline_error(payload, elapsed)
            except queue.Empty:
                break

        self.root.after(50, self._process_queues)

    def _on_pipeline_error(self, err_msg, elapsed):
        self._stop_search_button_animation(final_state="ERROR")
        self.lbl_app_status.config(text="Execution Error / Failed.", fg=self.C_RED)

        self._draw_blockchain_diagram(state="FAILED")
        self.lbl_bc_status.config(text=f"PIPELINE ERROR: {err_msg[:60]}", fg=self.C_RED, bg="#1a0808")
        self.bc_banner.config(highlightbackground=self.C_BORDER_RED)
        self.bc_panel_frame.config(highlightbackground=self.C_BORDER_RED)

        for child in self.results_container.winfo_children():
            child.destroy()

        lbl_err = tk.Label(
            self.results_container,
            text=f"[ ERROR OCCURRED ]\n{err_msg}",
            font=("Consolas", 10, "bold"),
            fg=self.C_RED,
            bg=self.C_PANEL,
            pady=30,
        )
        lbl_err.pack()

    def _on_pipeline_success(self, res, elapsed):
        self._stop_search_button_animation(final_state="COMPLETE")

        search_res = res.get("search_result", {})
        candidates = search_res.get("candidates", [])
        best_match = search_res.get("best_match")
        fingerprint = res.get("fingerprint") or search_res.get("fingerprint")
        tx_hash = res.get("transaction_hash")
        verified = res.get("verified", False)

        # ---------------------------------------------------------------------
        # 1. Update Blockchain Verification Panel (3 HONEST STATES)
        # ---------------------------------------------------------------------
        if fingerprint:
            self.lbl_fingerprint.config(text=f"{fingerprint[:24]}...{fingerprint[-12:]}", fg=self.C_CYAN)
        else:
            self.lbl_fingerprint.config(text="None generated", fg=self.C_TEXT_MUTED)

        # STATE A — VERIFIED
        if verified:
            self.lbl_app_status.config(text="Ready.", fg=self.C_GREEN)
            
            self.lbl_tx_hash.config(text=f"{tx_hash[:26]}...", fg=self.C_CYAN)
            self.lbl_block_num.config(text="1", fg=self.C_CYAN)

            self.lbl_ind_stored.config(text="✓ RECORD STORED", fg=self.C_GREEN)
            self.lbl_ind_retrieved.config(text="✓ RECORD RETRIEVED", fg=self.C_GREEN)
            self.lbl_ind_match.config(text="✓ FINGERPRINT MATCH", fg=self.C_GREEN)

            self.lbl_bc_status.config(text="✓ VERIFICATION SUCCESSFUL", fg="#000000", bg="#00e676")
            self.bc_banner.config(highlightbackground=self.C_BORDER_GREEN, bg="#00e676")
            self.bc_panel_frame.config(highlightbackground=self.C_BORDER_GREEN)
            self._draw_blockchain_diagram(state="SUCCESS", block_num=1)

        # STATE C — TRANSACTION CREATED BUT VERIFICATION FAILED
        elif tx_hash:
            self.lbl_app_status.config(text="Complete — Unverified.", fg=self.C_YELLOW)

            self.lbl_tx_hash.config(text=f"{tx_hash[:26]}...", fg=self.C_CYAN)
            self.lbl_block_num.config(text="1", fg=self.C_CYAN)

            self.lbl_ind_stored.config(text="✓ RECORD STORED", fg=self.C_GREEN)
            self.lbl_ind_retrieved.config(text="✓ RECORD RETRIEVED", fg=self.C_GREEN)
            self.lbl_ind_match.config(text="✕ FINGERPRINT MISMATCH", fg=self.C_RED)

            self.lbl_bc_status.config(text="✕ VERIFICATION FAILED", fg="#ffffff", bg="#cc0000")
            self.bc_banner.config(highlightbackground=self.C_BORDER_RED, bg="#cc0000")
            self.bc_panel_frame.config(highlightbackground=self.C_BORDER_RED)
            self._draw_blockchain_diagram(state="FAILED")

        # STATE B — GANACHE OFFLINE
        else:
            self.lbl_app_status.config(text="Complete — Ganache Offline.", fg=self.C_YELLOW)

            self.lbl_tx_hash.config(text="GANACHE OFFLINE", fg=self.C_RED)
            self.lbl_block_num.config(text="N/A", fg=self.C_TEXT_MUTED)

            self.lbl_ind_stored.config(text="✕ RECORD STORED", fg=self.C_RED)
            self.lbl_ind_retrieved.config(text="✕ RECORD RETRIEVED", fg=self.C_RED)
            self.lbl_ind_match.config(text="✕ FINGERPRINT MATCH", fg=self.C_RED)

            self.lbl_bc_status.config(text="✕ GANACHE OFFLINE — FINGERPRINT CREATED LOCALLY", fg="#ffffff", bg="#cc3300")
            self.bc_banner.config(highlightbackground=self.C_BORDER_RED, bg="#cc3300")
            self.bc_panel_frame.config(highlightbackground=self.C_BORDER_RED)
            self._draw_blockchain_diagram(state="OFFLINE")

        # ---------------------------------------------------------------------
        # 2. Update Search Statistics Panel
        # ---------------------------------------------------------------------
        fetched_count = sum(1 for c in candidates if c.get("image_verified", False))
        unavail_count = len(candidates) - fetched_count

        self.lbl_stat_cand.config(text=str(len(candidates)), fg=self.C_CYAN)
        self.lbl_stat_fetched.config(text=str(fetched_count), fg=self.C_GREEN)
        self.lbl_stat_unavail.config(text=str(unavail_count), fg=self.C_RED if unavail_count > 0 else self.C_TEXT_MUTED)
        self.lbl_stat_time.config(text=f"{elapsed:.2f}s", fg=self.C_YELLOW)

        # ---------------------------------------------------------------------
        # 3. Update Results & Matches Display (ALL MATCHES WITH BEST HIGHLIGHTED)
        # ---------------------------------------------------------------------
        for child in self.results_container.winfo_children():
            child.destroy()

        if not candidates:
            lbl_none = tk.Label(
                self.results_container,
                text="[ NO SEARCH MATCHES FOUND ]\nNo online candidates returned by Google Lens.",
                font=("Consolas", 10, "bold"),
                fg=self.C_RED,
                bg=self.C_PANEL,
                pady=40,
            )
            lbl_none.pack()
            return

        # Main scrollable canvas for ALL candidate matches
        res_canvas = tk.Canvas(self.results_container, bg=self.C_PANEL, highlightthickness=0)
        res_scrollbar = ttk.Scrollbar(self.results_container, orient=tk.VERTICAL, command=res_canvas.yview)
        res_content = tk.Frame(res_canvas, bg=self.C_PANEL)

        res_content.bind("<Configure>", lambda e: res_canvas.configure(scrollregion=res_canvas.bbox("all")))
        res_canvas.create_window((0, 0), window=res_content, anchor="nw")
        res_canvas.configure(yscrollcommand=res_scrollbar.set)

        res_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        res_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.cand_photos_tk.clear()

        # Iterate over ALL candidates returned by backend
        for idx, cand in enumerate(candidates, start=1):
            is_best = (cand == best_match) or (idx == 1 and best_match is None)

            cat_name = cand.get("match_category", "Related Result")
            cat_color = self.C_TEXT_MUTED
            cat_icon = "⚪"

            if cat_name == "Exact Image Match":
                cat_color = self.C_RED
                cat_icon = "🎯"
            elif cat_name == "Person Match":
                cat_color = self.C_CYAN
                cat_icon = "🔵"
            elif cat_name == "Visual Match":
                cat_color = self.C_YELLOW
                cat_icon = "🟡"

            border_c = self.C_RED if is_best else self.C_BORDER_MUTED
            bg_c = "#0a0000" if is_best else "#040407"

            card = tk.Frame(res_content, bg=bg_c, bd=1, relief=tk.SOLID, highlightbackground=border_c, highlightthickness=2 if is_best else 1, padx=8, pady=8)
            card.pack(fill=tk.X, pady=4)

            # Top header row of candidate card
            card_hdr = tk.Frame(card, bg=bg_c)
            card_hdr.pack(fill=tk.X, pady=(0, 4))

            if is_best:
                lbl_best_badge = tk.Label(card_hdr, text="🎯 BEST MATCH", font=("Consolas", 10, "bold"), fg="#ffffff", bg=self.C_RED, padx=6, pady=2)
                lbl_best_badge.pack(side=tk.LEFT, padx=(0, 8))

            lbl_rank = tk.Label(card_hdr, text=f"Rank #{cand.get('final_rank', idx)}", font=("Consolas", 9, "bold"), fg=self.C_YELLOW, bg=bg_c)
            lbl_rank.pack(side=tk.LEFT)

            cat_badge = tk.Label(card_hdr, text=f"{cat_icon} {cat_name}", font=("Consolas", 8, "bold"), fg=cat_color, bg=bg_c)
            cat_badge.pack(side=tk.RIGHT)

            # Body row: left thumbnail + right details
            card_body = tk.Frame(card, bg=bg_c)
            card_body.pack(fill=tk.X)

            img_frame = tk.Frame(card_body, bg="#000000", bd=1, relief=tk.SOLID, highlightbackground="#333333", highlightthickness=1, width=100, height=100)
            img_frame.pack(side=tk.LEFT, padx=(0, 8))
            img_frame.pack_propagate(False)

            lbl_c_img = tk.Label(img_frame, bg="#000000", text=f"#{idx}", font=("Consolas", 7), fg=self.C_TEXT_MUTED)
            lbl_c_img.pack(fill=tk.BOTH, expand=True)

            c_pil = cand.get("candidate_image")
            if c_pil:
                try:
                    c_copy = c_pil.copy()
                    c_copy.thumbnail((98, 98))
                    tk_c_photo = ImageTk.PhotoImage(c_copy)
                    self.cand_photos_tk.append(tk_c_photo)
                    lbl_c_img.config(image=tk_c_photo, text="")
                except Exception:
                    pass

            c_details = tk.Frame(card_body, bg=bg_c)
            c_details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            title_str = cand.get("title") or "Untitled Result"
            lbl_title = tk.Label(c_details, text=title_str, font=("Consolas", 9, "bold"), fg="#ffffff", bg=bg_c, anchor="w", justify=tk.LEFT, wraplength=340)
            lbl_title.pack(fill=tk.X, pady=(0, 2))

            p_str = f"Platform: {cand.get('platform', 'Web')}"
            tk.Label(c_details, text=p_str, font=("Consolas", 8), fg=self.C_TEXT, bg=bg_c, anchor="w").pack(fill=tk.X)

            conf_val = cand.get("confidence", 0.0)
            face_sim = cand.get("face_similarity", 0.0)
            vis_sim = cand.get("visual_similarity", 0.0)
            score_line = f"Confidence: {conf_val:.1f}%  |  Face: {face_sim:.1f}%  |  Visual: {vis_sim:.1f}%"
            tk.Label(c_details, text=score_line, font=("Consolas", 8, "bold"), fg=self.C_GREEN if conf_val >= 80 else self.C_YELLOW, bg=bg_c, anchor="w").pack(fill=tk.X, pady=(1, 3))

            target_url = cand.get("url", "")
            if target_url:
                btn_open_src = tk.Button(
                    c_details,
                    text=f"🔗 OPEN LINK ({target_url[:40]}...)",
                    font=("Consolas", 8, "underline"),
                    bg="#101018",
                    fg=self.C_CYAN,
                    activebackground="#202030",
                    activeforeground="#ffffff",
                    bd=0,
                    cursor="hand2",
                    anchor="w",
                    command=lambda u=target_url: webbrowser.open(u),
                )
                btn_open_src.pack(fill=tk.X)

                # Make the entire card clickable as requested!
                card.bind("<Button-1>", lambda e, u=target_url: webbrowser.open(u))
                lbl_title.bind("<Button-1>", lambda e, u=target_url: webbrowser.open(u))
                lbl_c_img.bind("<Button-1>", lambda e, u=target_url: webbrowser.open(u))


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    root = tk.Tk()
    app = RetroFaceSearchApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
