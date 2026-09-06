import os
import sys
import threading
import webbrowser
from io import BytesIO
from pathlib import Path

# Ensure project root is in sys.path for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

# Project imports
from reverse_search.face_id.face_id import detect_and_encode
from reverse_search.search import search_and_rank
from blockchain.write_record import write_fingerprint
from blockchain.verify_record import verify_fingerprint

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_pipeline(image_path, status_callback=None):
    """
    Executes the complete pipeline:
    1. Image Validation
    2. Face Detection & Embedding (optional)
    3. Google Lens Reverse Image Search & Ranking
    4. Deterministic SHA-256 Fingerprinting
    5. Ganache Blockchain Write
    6. Ganache Blockchain Verification
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Input image not found: {image_path}")

    def update_status(text):
        print(text)
        if status_callback:
            status_callback(text)

    update_status("1. Image loaded and validated [OK]")

    # Step 1: Face Analysis
    update_status("2. Analyzing face detection & encoding...")
    embedding = detect_and_encode(image_path, enforce_detection=False)

    if embedding is not None:
        update_status(f"   Face detected [OK] (FaceNet512 embedding: {len(embedding)}d)")
    else:
        update_status("   No face detected (Continuing with general visual search)")

    # Step 2: Reverse Search & Ranking
    update_status("3. Querying Google Lens & ranking candidates...")
    search_result = search_and_rank(image_path, input_face_embedding=embedding)

    update_status("4. Candidate discovery & ranking complete [OK]")

    # Step 3: Fingerprinting & Blockchain
    fingerprint = search_result["fingerprint"]
    update_status("5. SHA-256 fingerprint generated [OK]")

    update_status("6. Writing fingerprint to blockchain...")
    tx_hash = write_fingerprint(fingerprint)

    if tx_hash:
        update_status(f"   Blockchain transaction recorded [OK] ({tx_hash[:18]}...)")
        update_status("7. Verifying blockchain record...")
        verified = verify_fingerprint(tx_hash, fingerprint)
    else:
        update_status("   [Notice] Local Ganache node offline. Skipping on-chain write.")
        verified = False

    update_status("8. Pipeline execution complete [OK]")

    return {
        "image_path": str(image_path),
        "has_face": (embedding is not None),
        "search_result": search_result,
        "fingerprint": fingerprint,
        "transaction_hash": tx_hash,
        "verified": verified,
    }


# =========================================================
# TKINTER DESKTOP APPLICATION GUI
# =========================================================

class AppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Face Search + Blockchain Verification System")
        self.root.geometry("960x820")
        self.root.minsize(800, 650)

        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.selected_image_path = None
        self.preview_image_tk = None
        self.cand_images_tk = []

        self._build_ui()

    def _build_ui(self):
        # Header Frame
        header_frame = tk.Frame(self.root, bg="#1a1a2e", height=70)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False)

        header_label = tk.Label(
            header_frame,
            text="FACE SEARCH + BLOCKCHAIN VERIFICATION",
            font=("Helvetica", 16, "bold"),
            fg="#ffffff",
            bg="#1a1a2e",
        )
        header_label.pack(pady=18)

        # Main Scrollable Container
        main_canvas = tk.Canvas(self.root, highlightthickness=0, bg="#f4f6f9")
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)

        self.scroll_content = tk.Frame(main_canvas, bg="#f4f6f9")
        self.scroll_content.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all")),
        )

        main_canvas.create_window((0, 0), window=self.scroll_content, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # --- SECTION 1: Image Selection ---
        select_card = tk.LabelFrame(
            self.scroll_content,
            text=" 1. INPUT IMAGE SELECTION ",
            font=("Helvetica", 11, "bold"),
            bg="#ffffff",
            fg="#16213e",
            bd=1,
            relief=tk.SOLID,
            padx=15,
            pady=15,
        )
        select_card.pack(fill=tk.X, padx=20, pady=15)

        btn_select = tk.Button(
            select_card,
            text="Select Image (JPG, PNG, WebP)",
            font=("Helvetica", 10, "bold"),
            bg="#0f3460",
            fg="#ffffff",
            activebackground="#16213e",
            activeforeground="#ffffff",
            padx=12,
            pady=6,
            cursor="hand2",
            command=self._select_image,
        )
        btn_select.pack(anchor="w")

        self.lbl_file_path = tk.Label(
            select_card,
            text="No image selected",
            font=("Helvetica", 9, "italic"),
            fg="#666666",
            bg="#ffffff",
        )
        self.lbl_file_path.pack(anchor="w", pady=5)

        self.lbl_img_preview = tk.Label(select_card, bg="#eef2f5", width=140, height=140)
        self.lbl_img_preview.pack(anchor="w", pady=5)

        self.btn_search = tk.Button(
            select_card,
            text="SEARCH & VERIFY ON BLOCKCHAIN",
            font=("Helvetica", 11, "bold"),
            bg="#e94560",
            fg="#ffffff",
            activebackground="#c72c41",
            activeforeground="#ffffff",
            padx=16,
            pady=8,
            cursor="hand2",
            state=tk.DISABLED,
            command=self._start_search_thread,
        )
        self.btn_search.pack(anchor="w", pady=10)

        # --- SECTION 2: Pipeline Progress ---
        progress_card = tk.LabelFrame(
            self.scroll_content,
            text=" 2. PIPELINE PROGRESS ",
            font=("Helvetica", 11, "bold"),
            bg="#ffffff",
            fg="#16213e",
            bd=1,
            relief=tk.SOLID,
            padx=15,
            pady=15,
        )
        progress_card.pack(fill=tk.X, padx=20, pady=5)

        self.txt_log = tk.Text(
            progress_card,
            height=7,
            font=("Consolas", 9),
            bg="#1b1b2f",
            fg="#00fff5",
            bd=0,
            padx=10,
            pady=10,
        )
        self.txt_log.pack(fill=tk.X)
        self.txt_log.insert(tk.END, "Ready to start. Please select an image.\n")

        # --- SECTION 3: Results Display ---
        self.results_card = tk.LabelFrame(
            self.scroll_content,
            text=" 3. SEARCH & VERIFICATION RESULTS ",
            font=("Helvetica", 11, "bold"),
            bg="#ffffff",
            fg="#16213e",
            bd=1,
            relief=tk.SOLID,
            padx=15,
            pady=15,
        )
        self.results_card.pack(fill=tk.X, padx=20, pady=15)

        self.lbl_results_placeholder = tk.Label(
            self.results_card,
            text="Results will appear here after search completes.",
            font=("Helvetica", 10, "italic"),
            fg="#888888",
            bg="#ffffff",
        )
        self.lbl_results_placeholder.pack(pady=20)

    def _select_image(self):
        file_path = filedialog.askopenfilename(
            title="Select Image for Reverse Search",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.webp"),
                ("JPEG images", "*.jpg *.jpeg"),
                ("PNG images", "*.png"),
                ("WebP images", "*.webp"),
                ("All files", "*.*"),
            ],
        )

        if not file_path:
            return

        self.selected_image_path = file_path
        self.lbl_file_path.config(text=f"Selected: {file_path}", fg="#0f3460", font=("Helvetica", 9, "bold"))
        self.btn_search.config(state=tk.NORMAL)

        # Show thumbnail preview
        try:
            img = Image.open(file_path)
            img.thumbnail((140, 140))
            self.preview_image_tk = ImageTk.PhotoImage(img)
            self.lbl_img_preview.config(image=self.preview_image_tk, width=img.width, height=img.height)
        except Exception as e:
            self.lbl_img_preview.config(text="Preview error", image="")

    def _log(self, text):
        self.txt_log.insert(tk.END, text + "\n")
        self.txt_log.see(tk.END)

    def _start_search_thread(self):
        if not self.selected_image_path:
            return

        self.btn_search.config(state=tk.DISABLED)
        self.txt_log.delete("1.0", tk.END)
        self._log("Starting pipeline execution...")

        # Clear previous results
        for widget in self.results_card.winfo_children():
            widget.destroy()

        lbl_processing = tk.Label(
            self.results_card,
            text="Processing image & searching Google Lens... Please wait.",
            font=("Helvetica", 10, "bold"),
            fg="#0f3460",
            bg="#ffffff",
        )
        lbl_processing.pack(pady=20)

        # Run pipeline in background thread
        thread = threading.Thread(target=self._execute_pipeline, daemon=True)
        thread.start()

    def _execute_pipeline(self):
        try:
            res = run_pipeline(
                self.selected_image_path,
                status_callback=lambda msg: self.root.after(0, self._log, msg),
            )
            self.root.after(0, self._display_results, res)
        except Exception as e:
            self.root.after(0, self._log, f"\n[ERROR]: {e}")
            self.root.after(
                0,
                messagebox.showerror,
                "Pipeline Error",
                f"An error occurred during search:\n{e}",
            )
        finally:
            self.root.after(0, lambda: self.btn_search.config(state=tk.NORMAL))

    def _display_results(self, res):
        for widget in self.results_card.winfo_children():
            widget.destroy()

        search_res = res["search_result"]
        best = search_res.get("best_match")
        ranked = search_res.get("ranked_matches", [])

        # --- BEST MATCH CONTAINER ---
        best_frame = tk.LabelFrame(
            self.results_card,
            text=" BEST MATCH ",
            font=("Helvetica", 10, "bold"),
            bg="#eef5fc",
            fg="#0f3460",
            bd=1,
            relief=tk.SOLID,
            padx=10,
            pady=10,
        )
        best_frame.pack(fill=tk.X, pady=5)

        if best:
            info_frame = tk.Frame(best_frame, bg="#eef5fc")
            info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

            tk.Label(info_frame, text=f"Platform / Source: {best['platform']} ({best['source']})", font=("Helvetica", 10, "bold"), bg="#eef5fc", fg="#16213e", anchor="w").pack(fill=tk.X, pady=2)
            tk.Label(info_frame, text=f"Title: {best['title']}", font=("Helvetica", 9), bg="#eef5fc", anchor="w").pack(fill=tk.X, pady=2)
            tk.Label(info_frame, text=f"Match Type: {best['match_type']}", font=("Helvetica", 9), bg="#eef5fc", anchor="w").pack(fill=tk.X, pady=2)
            tk.Label(info_frame, text=f"Visual Match Confidence: {best['confidence']}%", font=("Helvetica", 10, "bold"), bg="#eef5fc", fg="#e94560", anchor="w").pack(fill=tk.X, pady=2)

            url_btn = tk.Button(
                info_frame, text=f"Open Link: {best['url'][:55]}...", font=("Helvetica", 8, "underline"), fg="#0f3460", bg="#eef5fc", bd=0, cursor="hand2", anchor="w",
                command=lambda u=best['url']: webbrowser.open(u)
            )
            url_btn.pack(fill=tk.X, pady=4)
        else:
            tk.Label(
                best_frame,
                text="No reliable online match found for this image.",
                font=("Helvetica", 10, "bold"),
                fg="#c72c41",
                bg="#eef5fc",
            ).pack(pady=10)

        # --- OTHER TOP CANDIDATES ---
        if len(ranked) > 1:
            candidates_frame = tk.LabelFrame(
                self.results_card,
                text=f" OTHER TOP CANDIDATES ({len(ranked) - 1}) ",
                font=("Helvetica", 10, "bold"),
                bg="#ffffff",
                fg="#16213e",
                padx=10,
                pady=10,
            )
            candidates_frame.pack(fill=tk.X, pady=10)

            for idx, cand in enumerate(ranked[1:4], start=2):
                c_box = tk.Frame(candidates_frame, bg="#f8f9fa", bd=1, relief=tk.GROOVE, padx=8, pady=6)
                c_box.pack(fill=tk.X, pady=3)

                c_text = f"Rank {idx} | {cand['platform']} | Confidence: {cand['confidence']}% | {cand['title'][:60]}"
                tk.Label(c_box, text=c_text, font=("Helvetica", 9), bg="#f8f9fa", anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

                btn_open = tk.Button(
                    c_box, text="Open Link", font=("Helvetica", 8), bg="#ffffff", command=lambda u=cand['url']: webbrowser.open(u)
                )
                btn_open.pack(side=tk.RIGHT)

        # --- BLOCKCHAIN VERIFICATION PANEL ---
        bc_frame = tk.LabelFrame(
            self.results_card,
            text=" BLOCKCHAIN RECORD & VERIFICATION ",
            font=("Helvetica", 10, "bold"),
            bg="#f0fdf4",
            fg="#166534",
            bd=1,
            relief=tk.SOLID,
            padx=10,
            pady=10,
        )
        bc_frame.pack(fill=tk.X, pady=10)

        fp_text = f"SHA-256 Fingerprint : {res['fingerprint']}"
        tk.Label(bc_frame, text=fp_text, font=("Consolas", 8, "bold"), bg="#f0fdf4", fg="#15803d", anchor="w").pack(fill=tk.X, pady=2)

        tx_str = res['transaction_hash'] if res['transaction_hash'] else "Offline (Ganache Not Connected)"
        tk.Label(bc_frame, text=f"Transaction Hash     : {tx_str}", font=("Consolas", 8), bg="#f0fdf4", fg="#166534", anchor="w").pack(fill=tk.X, pady=2)

        status_str = "BLOCKCHAIN VERIFIED [OK]" if res['verified'] else ("RECORD CREATED (UNVERIFIED)" if res['transaction_hash'] else "OFFLINE MODE (FINGERPRINT CREATED)")
        status_fg = "#15803d" if res['verified'] else "#b45309"
        tk.Label(bc_frame, text=f"Verification Status : {status_str}", font=("Helvetica", 10, "bold"), bg="#f0fdf4", fg=status_fg, anchor="w").pack(fill=tk.X, pady=4)


# =========================================================
# MAIN ENTRY POINT
# =========================================================

def main():
    # CLI Execution Mode if image path argument is supplied
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        img_arg = sys.argv[1]
        print("\n========================================")
        print("  FACE SEARCH + BLOCKCHAIN SYSTEM (CLI) ")
        print("========================================")
        print("Input file:", img_arg)
        res = run_pipeline(img_arg)
        print("\nPipeline finished successfully.")
        return

    # Tkinter Desktop GUI Execution Mode
    root = tk.Tk()
    app = AppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
