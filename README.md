# Billing Software

A simple local billing application with a graphical interface. It runs entirely
on your laptop, stores its data in CSV files, and generates PDF invoices.

Powered by SKV Softwares Pvt. Ltd.

---

## Features

- **Login with roles** — admin and normal users, with password-protected accounts.
- **Billing** — create bills, auto-generate a PDF invoice, and view it inside the app.
- **Customer management** — add customers and look them up by phone number or name.
- **Organization details** — set once (admin) and printed on every invoice.
- **PDF invoices** — saved automatically and openable/printable from the app.

---

## Requirements

- **Python 3** — download from <https://www.python.org/downloads/> and,
  during install, tick **"Add Python to PATH"**.
- **Python libraries** (one-time install). Open Command Prompt and run:

  ```
  pip install fpdf2 pymupdf pillow
  ```

  - `fpdf2` — required to create PDF invoices.
  - `pymupdf` + `pillow` — optional; used to preview invoices *inside* the app.
    Without them, invoices still open in your system's default PDF viewer.

---

## Running the application

**Option 1 — double-click** the file `run_billing.bat`.

**Option 2 — from Command Prompt:**

```
cd "%USERPROFILE%\Desktop\bill_software"
python billing_app.py
```

The main window maximizes automatically after you log in.

---

## First login

A default admin account is created automatically the first time you run the app:

| Username | Password   |
|----------|------------|
| `admin`  | `admin123` |

> **Change this password immediately** after logging in
> (Admin Mode → User Management → enter `admin` with a new password → Add / Update User).

---

## Using the app

### User Mode (all users)

- **Billing**
  - **Create a New Bill** — fill in the details and click **Save Bill + PDF**.
    You can auto-fill an existing customer by phone number or by name.
  - **Print a Bill** — browse all past transactions; select one and open its PDF
    (double-click also works). Admins can delete bills here (single or bulk).
- **Customer Management**
  - **Add a New Customer** — save a customer's name, phone, and address.
  - **View Existing Customers** — list all customers. Admins can delete them.

### Admin Mode (admin users only)

- **Organization Details** — your business name, address, phone, email, and
  GST/Tax number. These appear on every invoice.
- **User Management** — add, update, or delete login accounts and set their role
  (`user` or `admin`).

### Logout

The **Logout** button (top-right) lets you return to the login screen or exit
the application.

---

## Where your data is stored

Everything lives in this folder, next to `billing_app.py`:

```
bill_software/
├── billing_app.py       # the application
├── run_billing.bat      # launcher (no console window)
├── README.md            # this file
├── data/                # CSV "databases"
│   ├── bills.csv        # every saved bill
│   ├── customers.csv    # saved customers
│   ├── organization.csv # your organization details
│   └── users.csv        # login accounts (passwords are hashed)
└── invoices/            # generated PDF invoices
```

> **Backup tip:** to back up all your data, copy the `data/` and `invoices/`
> folders somewhere safe. The CSV files also open in Excel for reporting.

---

## Notes

- Passwords are stored as **SHA-256 hashes**, never as plain text.
- Deleting a bill also deletes its PDF file. Invoice numbers are not reused.
- Deleting a customer does **not** affect existing bills.

---

© 2026 SKV Softwares Pvt. Ltd. All rights reserved.
