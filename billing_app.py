#!/usr/bin/env python3
"""
Simple local billing software with Admin + User modes and PDF invoices.

Data files (all created automatically next to this script):
  - bills.csv       : every saved bill / invoice (the transaction database)
  - customers.csv   : saved customers, looked up by phone number
  - organization.txt: your organization details, shown on every invoice
  - invoices/       : generated PDF invoices

GUI: tkinter (built into Python).
PDF create : fpdf2                 ->  pip install fpdf2
PDF preview: PyMuPDF + Pillow      ->  pip install pymupdf pillow
             (optional - without them the PDF opens in your system viewer)

Run with:  python billing_app.py
"""

import csv
import os
import sys
import subprocess
import datetime
import hashlib
import glob
import tkinter as tk
from tkinter import ttk, messagebox

# ---------------------------------------------------------------------------
# File locations. CSV "databases" live in a "data" subfolder; generated PDF
# invoices live in an "invoices" subfolder. Both sit next to this script.
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
BILLS_FILE = os.path.join(DATA_DIR, "bills.csv")
CUSTOMERS_FILE = os.path.join(DATA_DIR, "customers.csv")
ORG_FILE = os.path.join(DATA_DIR, "organization.csv")
USERS_FILE = os.path.join(DATA_DIR, "users.csv")
INVOICE_DIR = os.path.join(BASE_DIR, "invoices")

# Column order for the bills CSV.
BILL_FIELDS = [
    "Invoice No",
    "Date",
    "Name",
    "Phone Number",
    "Address",
    "Service carried out",
    "Charges",
]

# Column order for the customers CSV.
CUSTOMER_FIELDS = ["Phone Number", "Name", "Address"]

# Organization detail fields (stored as key,value rows).
ORG_FIELDS = ["Organization Name", "Address", "Phone", "Email", "GST/Tax No"]

# Users CSV columns. Passwords are stored hashed, never in plain text.
USER_FIELDS = ["Username", "Password Hash", "Role"]

# Footer text shown at the bottom of every screen and on every invoice.
FOOTER_TEXT = "© 2026 SKV Softwares Pvt. Ltd. All rights reserved.  |  Powered by SKV Softwares Pvt. Ltd."


# ---------------------------------------------------------------------------
# CSV helpers.
# ---------------------------------------------------------------------------
def ensure_files():
    """Create data files with headers if they don't exist yet."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    if not os.path.exists(BILLS_FILE):
        with open(BILLS_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(BILL_FIELDS)
    if not os.path.exists(CUSTOMERS_FILE):
        with open(CUSTOMERS_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CUSTOMER_FIELDS)
    if not os.path.exists(INVOICE_DIR):
        os.makedirs(INVOICE_DIR)
    # Seed a default admin account the first time the app runs.
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(USER_FIELDS)
            writer.writerow(["admin", hash_password("admin123"), "admin"])


# ---------------------------------------------------------------------------
# User accounts and login.
# ---------------------------------------------------------------------------
def hash_password(password):
    """Return a SHA-256 hash of the password (so plain text is never stored)."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_users():
    """Return a dict keyed by username -> {hash, role}."""
    users = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                username = (row.get("Username") or "").strip()
                if username:
                    users[username] = {
                        "hash": row.get("Password Hash", ""),
                        "role": (row.get("Role") or "user").strip().lower(),
                    }
    return users


def save_users(users):
    """Persist the users dict to disk."""
    with open(USERS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(USER_FIELDS)
        for username, data in users.items():
            writer.writerow([username, data["hash"], data["role"]])


def check_login(username, password):
    """Return the role string if credentials are valid, else None."""
    user = load_users().get(username)
    if user and user["hash"] == hash_password(password):
        return user["role"]
    return None


def load_org():
    """Return organization details as a dict (empty strings if not set)."""
    org = {field: "" for field in ORG_FIELDS}
    if os.path.exists(ORG_FILE):
        with open(ORG_FILE, "r", newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0] in org:
                    org[row[0]] = row[1]
    return org


def save_org(org):
    """Persist organization details dict to disk."""
    with open(ORG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for field in ORG_FIELDS:
            writer.writerow([field, org.get(field, "")])


def load_customers():
    """Return a dict keyed by phone number -> {Name, Address}."""
    customers = {}
    if os.path.exists(CUSTOMERS_FILE):
        with open(CUSTOMERS_FILE, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                phone = (row.get("Phone Number") or "").strip()
                if phone:
                    customers[phone] = {
                        "Name": row.get("Name", ""),
                        "Address": row.get("Address", ""),
                    }
    return customers


def upsert_customer(phone, name, address):
    """Insert or update a customer keyed by phone number."""
    customers = load_customers()
    customers[phone] = {"Name": name, "Address": address}
    with open(CUSTOMERS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CUSTOMER_FIELDS)
        for ph, data in customers.items():
            writer.writerow([ph, data["Name"], data["Address"]])


def next_invoice_number():
    """Simple running invoice number based on rows already saved."""
    if not os.path.exists(BILLS_FILE):
        return 1
    with open(BILLS_FILE, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return max(1, len(rows))  # header counts as 1 -> first invoice is 1


# ---------------------------------------------------------------------------
# PDF invoice generation.
# ---------------------------------------------------------------------------
def generate_pdf(invoice_no, date, org, bill):
    """Create a PDF invoice and return its file path. Requires fpdf2."""
    try:
        from fpdf import FPDF
    except ImportError:
        raise RuntimeError(
            "The PDF library is not installed.\n\n"
            "Open Command Prompt and run:\n\n"
            "    pip install fpdf2\n\n"
            "Then try again."
        )

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # --- Organization header ---
    pdf.set_font("Helvetica", "B", 18)
    org_name = org.get("Organization Name") or "Your Organization"
    pdf.cell(0, 10, org_name, ln=True, align="C")

    pdf.set_font("Helvetica", "", 10)
    for key in ("Address", "Phone", "Email", "GST/Tax No"):
        value = org.get(key)
        if value:
            label = "GST/Tax No: " if key == "GST/Tax No" else ""
            pdf.cell(0, 5, f"{label}{value}", ln=True, align="C")

    pdf.ln(4)
    pdf.set_draw_color(120, 120, 120)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(6)

    # --- Invoice title + meta ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "INVOICE", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Invoice No: {invoice_no}", ln=True)
    pdf.cell(0, 6, f"Date: {date}", ln=True)
    pdf.ln(4)

    # --- Bill to ---
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "Bill To:", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Name: {bill['Name']}", ln=True)
    pdf.cell(0, 6, f"Phone: {bill['Phone Number']}", ln=True)
    if bill["Address"]:
        pdf.multi_cell(0, 6, f"Address: {bill['Address']}")
    pdf.ln(4)

    # --- Details table ---
    def section(title, text):
        if not text:
            return
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, title, ln=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, text)
        pdf.ln(2)

    section("Service carried out:", bill["Service carried out"])

    # --- Charges ---
    pdf.ln(4)
    pdf.set_draw_color(120, 120, 120)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    charges = bill["Charges"] or "0"
    pdf.cell(0, 8, f"Total Charges: {charges}", ln=True, align="R")

    # --- Footer ---
    pdf.ln(12)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 6, "Thank you for your business!", ln=True, align="C")

    safe_name = "".join(c for c in bill["Name"] if c.isalnum() or c in " _-").strip()
    filename = f"Invoice_{invoice_no}_{safe_name or 'customer'}.pdf"
    path = os.path.join(INVOICE_DIR, filename)
    pdf.output(path)
    return path


def add_footer(parent):
    """Pack a copyright / powered-by footer at the bottom of a window."""
    footer = tk.Frame(parent, bg="#f0f0f0")
    footer.pack(side="bottom", fill="x")
    tk.Label(footer, text=FOOTER_TEXT, bg="#f0f0f0", fg="gray",
             font=("Arial", 9)).pack(pady=4)
    return footer


def center_window(win):
    """Position a Toplevel/Tk window at the center of the screen."""
    win.update_idletasks()
    width = win.winfo_width()
    height = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry(f"+{x}+{y}")


def open_in_system_viewer(path):
    """Open a PDF using the operating system's default application."""
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class PdfPreview(tk.Toplevel):
    """A window that renders a PDF page-by-page inside the app.

    Uses PyMuPDF (fitz) + Pillow to rasterize pages. If those libraries are
    not installed, falls back to opening the PDF in the system viewer.
    """

    def __init__(self, parent, pdf_path):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.title(os.path.basename(pdf_path))
        self.geometry("640x800")

        try:
            import fitz  # PyMuPDF
            from PIL import Image, ImageTk
        except ImportError:
            self.destroy()
            open_in_system_viewer(pdf_path)
            messagebox.showinfo(
                "Opened in system viewer",
                "The invoice was opened in your default PDF viewer.\n\n"
                "To preview invoices inside this app instead, install:\n\n"
                "    pip install pymupdf pillow")
            return

        self._Image = Image
        self._ImageTk = ImageTk

        # Toolbar with a button to open externally / print.
        bar = tk.Frame(self)
        bar.pack(fill="x")
        tk.Button(bar, text="Open in system viewer / Print",
                  command=lambda: open_in_system_viewer(pdf_path)).pack(side="left", padx=6, pady=6)

        # Scrollable canvas holding the rendered pages.
        container = tk.Frame(self)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, background="#e0e0e0")
        vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, background="#e0e0e0")
        canvas.create_window((0, 0), window=inner, anchor="nw")

        # Render each page to an image and stack them vertically.
        self._photos = []  # keep references so images aren't garbage-collected
        doc = fitz.open(pdf_path)
        for page in doc:
            pix = page.get_pixmap(dpi=120)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            photo = ImageTk.PhotoImage(img)
            self._photos.append(photo)
            tk.Label(inner, image=photo, background="#e0e0e0").pack(pady=8)
        doc.close()

        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        # Mouse-wheel scrolling.
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))


# ---------------------------------------------------------------------------
# GUI.
# ---------------------------------------------------------------------------
class BillingApp:
    def __init__(self, root, username, role):
        self.root = root
        self.username = username
        self.role = role
        root.title(f"Billing Software  -  {username} ({role})")
        root.geometry("720x680")
        # Re-enable resizing/maximize (the login window had disabled it).
        root.resizable(True, True)
        # Maximize the window automatically after login.
        try:
            root.state("zoomed")            # Windows / most Linux
        except tk.TclError:
            try:
                root.attributes("-zoomed", True)  # some Linux window managers
            except tk.TclError:
                pass

        ensure_files()

        # Top bar with the logged-in user and a Logout button.
        topbar = tk.Frame(root)
        topbar.pack(fill="x")
        tk.Label(topbar, text=f"Logged in as: {username} ({role})",
                 font=("Arial", 10)).pack(side="left", padx=10, pady=6)
        tk.Button(topbar, text="Logout", font=("Arial", 10),
                  command=self.logout).pack(side="right", padx=10, pady=4)

        # Footer at the very bottom (packed before the notebook so it stays visible).
        add_footer(root)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)

        # Every logged-in user gets the User panel.
        self.user_tab = tk.Frame(notebook)
        notebook.add(self.user_tab, text="  User Mode  ")
        self.build_user_tab()

        # Only admins get the Admin panel.
        if role == "admin":
            self.admin_tab = tk.Frame(notebook)
            notebook.add(self.admin_tab, text="  Admin Mode  ")
            self.build_admin_tab()

    def logout(self):
        """Show a two-button dialog: return to login, or exit the application."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Logout")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()  # make it modal

        tk.Label(dialog, text="What would you like to do?",
                 font=("Arial", 12)).pack(padx=30, pady=(20, 15))

        btns = tk.Frame(dialog)
        btns.pack(padx=30, pady=(0, 20))
        tk.Button(btns, text="Return to Login Screen", width=22,
                  font=("Arial", 10), command=lambda: self._do_logout(dialog)
                  ).grid(row=0, column=0, padx=8)
        tk.Button(btns, text="Exit Application", width=22, bg="#c62828", fg="white",
                  font=("Arial", 10, "bold"), command=self.root.destroy
                  ).grid(row=0, column=1, padx=8)

        center_window(dialog)

    def _do_logout(self, dialog):
        """Tear down the session and return to the login screen."""
        dialog.destroy()
        for widget in self.root.winfo_children():
            widget.destroy()
        # Un-maximize before showing the small login window.
        try:
            self.root.state("normal")
        except tk.TclError:
            pass
        self.root.resizable(False, False)
        LoginWindow(self.root)

    # ------------------------------------------------------------------
    # ADMIN TAB
    # ------------------------------------------------------------------
    def build_admin_tab(self):
        # Admin Mode has two sub-tabs: Organization Details and User Management.
        admin_nb = ttk.Notebook(self.admin_tab)
        admin_nb.pack(fill="both", expand=True)

        self.org_subtab = tk.Frame(admin_nb)
        self.users_subtab = tk.Frame(admin_nb)
        admin_nb.add(self.org_subtab, text="  Organization Details  ")
        admin_nb.add(self.users_subtab, text="  User Management  ")

        self.build_org_subtab()
        self.build_users_subtab()

    def build_org_subtab(self):
        frame = self.org_subtab
        tk.Label(frame, text="Organization Details",
                 font=("Arial", 16, "bold")).pack(pady=(20, 5))
        tk.Label(frame, text="These details appear on every invoice.",
                 fg="gray").pack(pady=(0, 15))

        form = tk.Frame(frame)
        form.pack(padx=30, pady=10, fill="x")

        org = load_org()
        self.org_entries = {}
        for row, field in enumerate(ORG_FIELDS):
            tk.Label(form, text=field + ":", width=18, anchor="w",
                     font=("Arial", 11)).grid(row=row, column=0, sticky="nw", pady=8)
            if field == "Address":
                widget = tk.Text(form, width=40, height=3, font=("Arial", 11))
                widget.insert("1.0", org.get(field, ""))
            else:
                widget = tk.Entry(form, width=42, font=("Arial", 11))
                widget.insert(0, org.get(field, ""))
            widget.grid(row=row, column=1, pady=8, sticky="w")
            self.org_entries[field] = widget

        tk.Button(frame, text="Save Organization Details", width=24,
                  bg="#1565c0", fg="white", font=("Arial", 11, "bold"),
                  command=self.save_org_details).pack(pady=20)

    def build_users_subtab(self):
        frame = self.users_subtab
        # --- User account management ---
        tk.Label(frame, text="Manage Login Accounts",
                 font=("Arial", 16, "bold")).pack(pady=(20, 10))

        umf = tk.Frame(frame)
        umf.pack(padx=30, pady=5)

        tk.Label(umf, text="Username:", font=("Arial", 11)).grid(row=0, column=0, padx=5, pady=4)
        self.new_username = tk.Entry(umf, width=20, font=("Arial", 11))
        self.new_username.grid(row=0, column=1, padx=5, pady=4)

        tk.Label(umf, text="Password:", font=("Arial", 11)).grid(row=0, column=2, padx=5, pady=4)
        self.new_password = tk.Entry(umf, width=20, show="*", font=("Arial", 11))
        self.new_password.grid(row=0, column=3, padx=5, pady=4)

        tk.Label(umf, text="Role:", font=("Arial", 11)).grid(row=1, column=0, padx=5, pady=4)
        self.new_role = ttk.Combobox(umf, width=17, values=["user", "admin"],
                                     state="readonly", font=("Arial", 11))
        self.new_role.set("user")
        self.new_role.grid(row=1, column=1, padx=5, pady=4)

        tk.Button(umf, text="Add / Update User", bg="#2e7d32", fg="white",
                  font=("Arial", 10, "bold"),
                  command=self.add_user).grid(row=1, column=2, padx=5, pady=4)
        tk.Button(umf, text="Delete User", font=("Arial", 10),
                  command=self.delete_user).grid(row=1, column=3, padx=5, pady=4)

        tk.Button(frame, text="View Users", font=("Arial", 10),
                  command=self.view_users).pack(pady=8)

    def add_user(self):
        username = self.new_username.get().strip()
        password = self.new_password.get()
        role = self.new_role.get().strip().lower() or "user"
        if not username or not password:
            messagebox.showwarning("Missing", "Enter both a username and a password.")
            return
        users = load_users()
        existed = username in users
        users[username] = {"hash": hash_password(password), "role": role}
        save_users(users)
        self.new_username.delete(0, "end")
        self.new_password.delete(0, "end")
        action = "updated" if existed else "created"
        messagebox.showinfo("Saved", f"User '{username}' {action} with role '{role}'.")

    def delete_user(self):
        username = self.new_username.get().strip()
        if not username:
            messagebox.showwarning("Missing", "Enter the username to delete.")
            return
        if username == self.username:
            messagebox.showwarning("Not allowed", "You cannot delete the account you are logged in with.")
            return
        users = load_users()
        if username not in users:
            messagebox.showinfo("Not found", f"No user named '{username}'.")
            return
        admins = [u for u, d in users.items() if d["role"] == "admin"]
        if users[username]["role"] == "admin" and len(admins) <= 1:
            messagebox.showwarning("Not allowed", "Cannot delete the last remaining admin.")
            return
        del users[username]
        save_users(users)
        self.new_username.delete(0, "end")
        messagebox.showinfo("Deleted", f"User '{username}' deleted.")

    def view_users(self):
        users = load_users()
        win = tk.Toplevel(self.root)
        win.title("User Accounts")
        win.geometry("400x300")
        tree = ttk.Treeview(win, columns=["Username", "Role"], show="headings")
        tree.heading("Username", text="Username")
        tree.heading("Role", text="Role")
        tree.column("Username", width=200)
        tree.column("Role", width=120)
        for username, data in users.items():
            tree.insert("", "end", values=[username, data["role"]])
        tree.pack(fill="both", expand=True, padx=10, pady=10)

    def save_org_details(self):
        org = {}
        for field, widget in self.org_entries.items():
            if isinstance(widget, tk.Text):
                org[field] = widget.get("1.0", "end").strip()
            else:
                org[field] = widget.get().strip()
        if not org.get("Organization Name"):
            messagebox.showwarning("Missing", "Please enter the Organization Name.")
            return
        save_org(org)
        messagebox.showinfo("Saved", "Organization details saved.")

    # ------------------------------------------------------------------
    # USER TAB
    #   Billing              -> Create a New Bill / Print a Bill
    #   Customer Management  -> View existing customers / Add a new customer
    # ------------------------------------------------------------------
    def build_user_tab(self):
        user_nb = ttk.Notebook(self.user_tab)
        user_nb.pack(fill="both", expand=True)

        billing_tab = tk.Frame(user_nb)
        customer_tab = tk.Frame(user_nb)
        user_nb.add(billing_tab, text="  Billing  ")
        user_nb.add(customer_tab, text="  Customer Management  ")

        # --- Billing sub-tabs ---
        billing_nb = ttk.Notebook(billing_tab)
        billing_nb.pack(fill="both", expand=True)
        self.bill_subtab = tk.Frame(billing_nb)
        self.print_subtab = tk.Frame(billing_nb)
        billing_nb.add(self.bill_subtab, text="  Create a New Bill  ")
        billing_nb.add(self.print_subtab, text="  Print a Bill  ")
        self.build_bill_subtab()
        self.build_print_subtab()

        # --- Customer Management sub-tabs ---
        customer_nb = ttk.Notebook(customer_tab)
        customer_nb.pack(fill="both", expand=True)
        self.newcust_subtab = tk.Frame(customer_nb)
        self.viewcust_subtab = tk.Frame(customer_nb)
        customer_nb.add(self.newcust_subtab, text="  Add a New Customer  ")
        customer_nb.add(self.viewcust_subtab, text="  View Existing Customers  ")
        self.build_newcustomer_subtab()
        self.build_viewcustomers_subtab()

        # Auto-refresh lists when their tab is opened.
        billing_nb.bind("<<NotebookTabChanged>>",
                        lambda e: self._on_subtab_changed(e, self.print_subtab,
                                                          self.refresh_transactions))
        customer_nb.bind("<<NotebookTabChanged>>",
                         lambda e: self._on_subtab_changed(e, self.viewcust_subtab,
                                                           self.refresh_customers))

    def _on_subtab_changed(self, event, target_frame, refresh_fn):
        if event.widget.select() == str(target_frame):
            refresh_fn()

    # ---- generic form helpers (work on any {label: widget} dict) ----
    @staticmethod
    def _get(entries, label):
        widget = entries[label]
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end").strip()
        return widget.get().strip()

    @staticmethod
    def _set(entries, label, value):
        widget = entries[label]
        if isinstance(widget, tk.Text):
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        else:
            widget.delete(0, "end")
            widget.insert(0, value)

    @staticmethod
    def _clear(entries):
        for label in entries:
            BillingApp._set(entries, label, "")

    @staticmethod
    def _build_form(parent, fields):
        """Build a labelled form; return a {label: widget} dict."""
        entries = {}
        for row, (label, lines) in enumerate(fields):
            tk.Label(parent, text=label + ":", width=18, anchor="nw",
                     font=("Arial", 11)).grid(row=row, column=0, sticky="nw", pady=6)
            if lines > 1:
                widget = tk.Text(parent, width=42, height=lines, font=("Arial", 11))
            else:
                widget = tk.Entry(parent, width=44, font=("Arial", 11))
            widget.grid(row=row, column=1, pady=6, sticky="w")
            entries[label] = widget
        return entries

    # ==================================================================
    # Customer Management: Add a New Customer
    # ==================================================================
    def build_newcustomer_subtab(self):
        frame = self.newcust_subtab
        tk.Label(frame, text="Add a New Customer",
                 font=("Arial", 16, "bold")).pack(pady=(20, 15))

        form = tk.Frame(frame)
        form.pack(padx=25, pady=10)
        self.cust_entries = self._build_form(
            form, [("Name", 1), ("Phone Number", 1), ("Address", 2)])

        btns = tk.Frame(frame)
        btns.pack(pady=15)
        tk.Button(btns, text="Save Customer", width=16, bg="#2e7d32", fg="white",
                  font=("Arial", 11, "bold"),
                  command=self.save_customer).grid(row=0, column=0, padx=6)
        tk.Button(btns, text="Clear", width=12, font=("Arial", 10),
                  command=lambda: self._clear(self.cust_entries)).grid(row=0, column=1, padx=6)

        tk.Label(frame, text="Tip: saving a bill also stores/updates the customer automatically.",
                 fg="gray", font=("Arial", 9)).pack(pady=10)

    def save_customer(self):
        """Add a new customer or update an existing one (keyed by phone)."""
        name = self._get(self.cust_entries, "Name")
        phone = self._get(self.cust_entries, "Phone Number")
        address = self._get(self.cust_entries, "Address")
        if not phone:
            messagebox.showwarning("Missing", "Phone Number is required to save a customer.")
            return
        if not name:
            messagebox.showwarning("Missing", "Please enter a Name.")
            return
        existed = phone in load_customers()
        upsert_customer(phone, name, address)
        self.refresh_customers()
        action = "updated" if existed else "added"
        messagebox.showinfo("Saved", f"Customer {name} {action}.")

    # ==================================================================
    # Customer Management: View Existing Customers (with bulk delete)
    # ==================================================================
    def build_viewcustomers_subtab(self):
        frame = self.viewcust_subtab
        tk.Label(frame, text="Existing Customers",
                 font=("Arial", 16, "bold")).pack(pady=(15, 5))

        bar = tk.Frame(frame)
        bar.pack(pady=6)
        tk.Button(bar, text="Refresh List", font=("Arial", 10),
                  command=self.refresh_customers).grid(row=0, column=0, padx=6)
        # Deleting customers is admin-only; grayed out for normal users.
        delete_state = "normal" if self.role == "admin" else "disabled"
        tk.Button(bar, text="Delete Selected Customer(s)", bg="#c62828", fg="white",
                  font=("Arial", 10, "bold"), state=delete_state,
                  command=self.delete_selected_customers).grid(row=0, column=1, padx=6)

        tip = ("Tip: hold Ctrl or Shift to select multiple customers for bulk delete."
               if self.role == "admin"
               else "Note: deleting customers is available to admin users only.")
        tk.Label(frame, text=tip, fg="gray", font=("Arial", 9)).pack()

        tree_frame = tk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.cust_tree = ttk.Treeview(tree_frame, columns=CUSTOMER_FIELDS,
                                      show="headings", selectmode="extended")
        for col in CUSTOMER_FIELDS:
            self.cust_tree.heading(col, text=col)
            self.cust_tree.column(col, width=200, anchor="w")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.cust_tree.yview)
        self.cust_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.cust_tree.pack(side="left", fill="both", expand=True)

        self.refresh_customers()

    def refresh_customers(self):
        """Reload all customers from customers.csv into the table."""
        if not hasattr(self, "cust_tree"):
            return
        self.cust_tree.delete(*self.cust_tree.get_children())
        for phone, data in load_customers().items():
            self.cust_tree.insert("", "end",
                                  values=[phone, data["Name"], data["Address"]])

    def delete_selected_customers(self):
        """Delete one or many selected customers from customers.csv."""
        selection = self.cust_tree.selection()
        if not selection:
            messagebox.showinfo("Select a customer",
                                "Please select one or more customers to delete.")
            return

        phones = {self.cust_tree.item(item, "values")[0] for item in selection}
        count = len(phones)
        if not messagebox.askyesno(
                "Confirm delete",
                f"Delete {count} selected customer(s)?\n\n"
                "This only removes them from the customer list.\n"
                "Existing bills are not affected. This cannot be undone."):
            return

        customers = load_customers()
        for phone in phones:
            customers.pop(phone, None)
        # Rewrite the customers file.
        with open(CUSTOMERS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CUSTOMER_FIELDS)
            for phone, data in customers.items():
                writer.writerow([phone, data["Name"], data["Address"]])

        self.refresh_customers()
        messagebox.showinfo("Deleted", f"{count} customer(s) deleted.")

    # ==================================================================
    # SUB-TAB 2: Create Bill
    # ==================================================================
    def build_bill_subtab(self):
        frame = self.bill_subtab
        tk.Label(frame, text="Create a Bill",
                 font=("Arial", 16, "bold")).pack(pady=(15, 5))

        # --- Fetch existing customer by phone ---
        search = tk.Frame(frame)
        search.pack(pady=8)

        # Fetch existing customer by phone number.
        tk.Label(search, text="Fetch by phone:",
                 font=("Arial", 11)).grid(row=0, column=0, padx=5, pady=3, sticky="e")
        self.search_entry = tk.Entry(search, width=20, font=("Arial", 11))
        self.search_entry.grid(row=0, column=1, padx=5, pady=3)
        tk.Button(search, text="Fetch Customer",
                  command=self.fetch_customer).grid(row=0, column=2, padx=5, pady=3)

        # Fetch existing customer by name.
        tk.Label(search, text="Fetch by name:",
                 font=("Arial", 11)).grid(row=1, column=0, padx=5, pady=3, sticky="e")
        self.search_name_entry = tk.Entry(search, width=20, font=("Arial", 11))
        self.search_name_entry.grid(row=1, column=1, padx=5, pady=3)
        tk.Button(search, text="Fetch Customer",
                  command=self.fetch_customer_by_name).grid(row=1, column=2, padx=5, pady=3)

        form = tk.Frame(frame)
        form.pack(padx=25, pady=10)
        self.entries = self._build_form(form, [
            ("Name", 1),
            ("Phone Number", 1),
            ("Address", 2),
            ("Service carried out", 1),
            ("Charges", 1),
        ])

        btns = tk.Frame(frame)
        btns.pack(pady=12)
        tk.Button(btns, text="Save Bill + PDF", width=16, bg="#2e7d32",
                  fg="white", font=("Arial", 11, "bold"),
                  command=self.save_bill).grid(row=0, column=0, padx=6)
        tk.Button(btns, text="Clear", width=12, font=("Arial", 10),
                  command=lambda: self._clear(self.entries)).grid(row=0, column=1, padx=6)

    def fetch_customer(self):
        phone = self.search_entry.get().strip()
        if not phone:
            messagebox.showwarning("Enter phone", "Type a phone number to search.")
            return
        cust = load_customers().get(phone)
        if not cust:
            messagebox.showinfo("Not found",
                                f"No customer found with phone {phone}.\n"
                                "Use the 'New Customer' tab to add them, or just type the details.")
            return
        self._set(self.entries, "Name", cust["Name"])
        self._set(self.entries, "Phone Number", phone)
        self._set(self.entries, "Address", cust["Address"])
        messagebox.showinfo("Found", f"Loaded details for {cust['Name']}.")

    def fetch_customer_by_name(self):
        """Find customers by name (case-insensitive, partial match).

        If several match, show a picker so the user can choose one.
        """
        name = self.search_name_entry.get().strip()
        if not name:
            messagebox.showwarning("Enter name", "Type a name to search.")
            return
        query = name.lower()
        # Each match is (phone, name, address).
        matches = [(phone, data["Name"], data["Address"])
                   for phone, data in load_customers().items()
                   if query in data["Name"].lower()]

        if not matches:
            messagebox.showinfo("Not found",
                                f"No customer found matching '{name}'.")
            return
        if len(matches) == 1:
            self._load_customer_into_form(matches[0])
            return
        # Multiple matches -> let the user pick one.
        self._pick_customer(matches)

    def _load_customer_into_form(self, match):
        phone, cname, address = match
        self._set(self.entries, "Name", cname)
        self._set(self.entries, "Phone Number", phone)
        self._set(self.entries, "Address", address)
        messagebox.showinfo("Found", f"Loaded details for {cname}.")

    def _pick_customer(self, matches):
        """Modal dialog listing matching customers; loads the chosen one."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Select a customer")
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text=f"{len(matches)} customers matched. Select one:",
                 font=("Arial", 11)).pack(padx=15, pady=(15, 8))

        tree_frame = tk.Frame(dialog)
        tree_frame.pack(fill="both", expand=True, padx=15)
        tree = ttk.Treeview(tree_frame, columns=CUSTOMER_FIELDS,
                            show="headings", height=8, selectmode="browse")
        for col in CUSTOMER_FIELDS:
            tree.heading(col, text=col)
            tree.column(col, width=180, anchor="w")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        # Store phone,name,address in tree order (columns are phone,name,address).
        for phone, cname, address in matches:
            tree.insert("", "end", values=[phone, cname, address])

        def choose():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Select", "Please select a customer.", parent=dialog)
                return
            phone, cname, address = tree.item(sel[0], "values")
            dialog.destroy()
            self._load_customer_into_form((phone, cname, address))

        tree.bind("<Double-1>", lambda e: choose())

        btns = tk.Frame(dialog)
        btns.pack(pady=12)
        tk.Button(btns, text="Select", width=12, bg="#2e7d32", fg="white",
                  font=("Arial", 10, "bold"), command=choose).grid(row=0, column=0, padx=6)
        tk.Button(btns, text="Cancel", width=12, font=("Arial", 10),
                  command=dialog.destroy).grid(row=0, column=1, padx=6)

        dialog.geometry("600x350")
        center_window(dialog)

    def save_bill(self):
        name = self._get(self.entries, "Name")
        phone = self._get(self.entries, "Phone Number")
        charges = self._get(self.entries, "Charges")

        if not name:
            messagebox.showwarning("Missing information", "Please enter a Name.")
            return
        if charges:
            try:
                float(charges)
            except ValueError:
                messagebox.showwarning("Invalid charges",
                                       "Charges should be a number (e.g. 250 or 250.50).")
                return

        invoice_no = next_invoice_number()
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        bill = {
            "Name": name,
            "Phone Number": phone,
            "Address": self._get(self.entries, "Address"),
            "Service carried out": self._get(self.entries, "Service carried out"),
            "Charges": charges,
        }

        # Save the bill row.
        row = [invoice_no, date, name, phone, bill["Address"],
               bill["Service carried out"], charges]
        with open(BILLS_FILE, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

        # Auto-save/update the customer too.
        if phone:
            upsert_customer(phone, name, bill["Address"])

        # Generate the PDF invoice and open it inside the app.
        try:
            org = load_org()
            path = generate_pdf(invoice_no, date, org, bill)
            self._clear(self.entries)
            PdfPreview(self.root, path)  # open the bill in-app as PDF
        except RuntimeError as e:
            messagebox.showwarning("Bill saved, PDF skipped", str(e))
            self._clear(self.entries)

    # ==================================================================
    # SUB-TAB 3: Print Bill  (browse all transactions, open any invoice)
    # ==================================================================
    def build_print_subtab(self):
        frame = self.print_subtab
        tk.Label(frame, text="Print / View Bills",
                 font=("Arial", 16, "bold")).pack(pady=(15, 5))

        bar = tk.Frame(frame)
        bar.pack(pady=6)
        tk.Button(bar, text="Refresh List", font=("Arial", 10),
                  command=self.refresh_transactions).grid(row=0, column=0, padx=6)
        tk.Button(bar, text="Open Selected Bill (PDF)", bg="#1565c0", fg="white",
                  font=("Arial", 10, "bold"),
                  command=self.open_selected_bill).grid(row=0, column=1, padx=6)
        # Deleting bills is admin-only; grayed out for normal users.
        delete_state = "normal" if self.role == "admin" else "disabled"
        tk.Button(bar, text="Delete Selected Bill(s)", bg="#c62828", fg="white",
                  font=("Arial", 10, "bold"), state=delete_state,
                  command=self.delete_selected_bills).grid(row=0, column=2, padx=6)

        tip = ("Tip: hold Ctrl or Shift to select multiple bills for bulk delete."
               if self.role == "admin"
               else "Note: deleting bills is available to admin users only.")
        tk.Label(frame, text=tip, fg="gray", font=("Arial", 9)).pack()

        tree_frame = tk.Frame(frame)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.txn_tree = ttk.Treeview(tree_frame, columns=BILL_FIELDS,
                                     show="headings", selectmode="extended")
        for col in BILL_FIELDS:
            self.txn_tree.heading(col, text=col)
            width = 70 if col == "Invoice No" else 130
            self.txn_tree.column(col, width=width, anchor="w")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.txn_tree.yview)
        self.txn_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.txn_tree.pack(side="left", fill="both", expand=True)

        # Double-click a row to open its PDF.
        self.txn_tree.bind("<Double-1>", lambda e: self.open_selected_bill())

        self.refresh_transactions()

    def refresh_transactions(self):
        """Reload all transactions from bills.csv into the table."""
        if not hasattr(self, "txn_tree"):
            return
        self.txn_tree.delete(*self.txn_tree.get_children())
        if not os.path.exists(BILLS_FILE):
            return
        with open(BILLS_FILE, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        for data_row in rows[1:]:  # skip header
            self.txn_tree.insert("", "end", values=data_row)

    def _find_invoice_pdf(self, invoice_no):
        """Return the PDF path for an invoice number, or None."""
        matches = glob.glob(os.path.join(INVOICE_DIR, f"Invoice_{invoice_no}_*.pdf"))
        return matches[0] if matches else None

    def open_selected_bill(self):
        selection = self.txn_tree.selection()
        if not selection:
            messagebox.showinfo("Select a bill", "Please select a transaction from the list.")
            return
        values = self.txn_tree.item(selection[0], "values")
        invoice_no = values[0]
        path = self._find_invoice_pdf(invoice_no)
        if not path:
            # The PDF may not exist (e.g. saved before fpdf2 was installed).
            if messagebox.askyesno(
                    "PDF not found",
                    f"No saved PDF for Invoice {invoice_no}.\n\nRegenerate it now?"):
                path = self._regenerate_pdf(values)
                if not path:
                    return
            else:
                return
        PdfPreview(self.root, path)

    def _regenerate_pdf(self, values):
        """Rebuild a PDF from a stored bill row (used if the file is missing)."""
        record = dict(zip(BILL_FIELDS, values))
        bill = {
            "Name": record.get("Name", ""),
            "Phone Number": record.get("Phone Number", ""),
            "Address": record.get("Address", ""),
            "Service carried out": record.get("Service carried out", ""),
            "Charges": record.get("Charges", ""),
        }
        try:
            return generate_pdf(record.get("Invoice No", ""),
                                record.get("Date", ""), load_org(), bill)
        except RuntimeError as e:
            messagebox.showwarning("Cannot create PDF", str(e))
            return None

    def delete_selected_bills(self):
        """Delete one or many selected bills (CSV rows + their PDF files)."""
        selection = self.txn_tree.selection()
        if not selection:
            messagebox.showinfo("Select a bill",
                                "Please select one or more transactions to delete.")
            return

        # Collect the invoice numbers to remove.
        invoice_nos = {self.txn_tree.item(item, "values")[0] for item in selection}
        count = len(invoice_nos)

        prompt = (f"Delete {count} selected bill(s)?\n\n"
                  "This removes the record from bills.csv and deletes the PDF file(s).\n"
                  "This cannot be undone.")
        if not messagebox.askyesno("Confirm delete", prompt):
            return

        # Rewrite bills.csv without the selected rows.
        with open(BILLS_FILE, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        header, data_rows = rows[0], rows[1:]
        kept = [r for r in data_rows if not (r and r[0] in invoice_nos)]
        with open(BILLS_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(kept)

        # Delete the matching PDF files (ignore ones that don't exist).
        for invoice_no in invoice_nos:
            path = self._find_invoice_pdf(invoice_no)
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

        self.refresh_transactions()
        messagebox.showinfo("Deleted", f"{count} bill(s) deleted.")


class LoginWindow:
    """First screen: ask for username/password, then open the main app."""

    def __init__(self, root):
        self.root = root
        root.title("Billing Software - Login")
        root.geometry("560x280")
        root.resizable(False, False)

        ensure_files()

        tk.Label(root, text="Login", font=("Arial", 18, "bold")).pack(pady=(25, 15))

        form = tk.Frame(root)
        form.pack()

        tk.Label(form, text="Username:", font=("Arial", 11)).grid(row=0, column=0, padx=8, pady=8, sticky="e")
        self.username = tk.Entry(form, width=22, font=("Arial", 11))
        self.username.grid(row=0, column=1, padx=8, pady=8)

        tk.Label(form, text="Password:", font=("Arial", 11)).grid(row=1, column=0, padx=8, pady=8, sticky="e")
        self.password = tk.Entry(form, width=22, show="*", font=("Arial", 11))
        self.password.grid(row=1, column=1, padx=8, pady=8)

        tk.Button(root, text="Login", width=14, bg="#1565c0", fg="white",
                  font=("Arial", 11, "bold"), command=self.attempt_login).pack(pady=15)

        # Footer with copyright / powered-by mark.
        add_footer(root)

        # Press Enter to log in.
        root.bind("<Return>", lambda event: self.attempt_login())
        self.username.focus()

        # Always show the login window centered on the screen.
        center_window(root)

    def attempt_login(self):
        username = self.username.get().strip()
        password = self.password.get()
        role = check_login(username, password)
        if role is None:
            messagebox.showerror("Login failed", "Invalid username or password.")
            self.password.delete(0, "end")
            return
        # Tear down the login screen and open the main app in the same window.
        self.root.unbind("<Return>")
        for widget in self.root.winfo_children():
            widget.destroy()
        BillingApp(self.root, username, role)


if __name__ == "__main__":
    root = tk.Tk()
    LoginWindow(root)
    root.mainloop()
