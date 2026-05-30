"""
╔══════════════════════════════════════════════════════════════════╗
║        AUTOMATED HELPDESK REASONER — Terminal Edition           ║
║        B.Tech AI / Data Science Project Demonstration           ║
╚══════════════════════════════════════════════════════════════════╝

Run:  python helpdesk.py

Features:
  • Submit a support ticket (auto-classify, prioritise, solve)
  • View all tickets in a formatted table
  • Filter tickets by category, priority, or status
  • Mark tickets as Resolved
  • Delete a ticket
  • All data persisted in SQLite (helpdesk.db)
"""

import sqlite3
import uuid
import os
import sys
from datetime import datetime

# ── Try to import 'rich' for coloured TUI; fall back to plain text ──
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich import box
    from rich.text import Text
    from rich.columns import Columns
    from rich.rule import Rule
    RICH = True
except ImportError:
    RICH = False

# ─────────────────────────────────────────────────────────────────
# 1. DATABASE SETUP
# ─────────────────────────────────────────────────────────────────
DATABASE = "helpdesk.db"


def get_connection():
    """Opens and returns a SQLite connection with Row factory."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Creates the tickets table if it doesn't exist.
    Called once at startup.

    Schema:
      ticket_id  – Unique human-readable ID  (e.g. TKT-A1B2C3D4)
      name       – Reporter's full name
      email      – Reporter's email
      query      – Raw issue description
      category   – Classified: Network / Login / Software / Hardware / Other
      priority   – Critical / High / Medium / Low
      solution   – Predefined step-by-step fix
      status     – Open / Resolved
      created_at – ISO timestamp
    """
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id  TEXT NOT NULL UNIQUE,
            name       TEXT NOT NULL,
            email      TEXT NOT NULL,
            query      TEXT NOT NULL,
            category   TEXT NOT NULL,
            priority   TEXT NOT NULL,
            solution   TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'Open',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────
# 2. CLASSIFICATION ENGINE
# ─────────────────────────────────────────────────────────────────

# Keyword sets per category — more hits = stronger match
CATEGORY_KEYWORDS = {
    "Network": [
        "internet", "wifi", "network", "connection", "offline", "dns",
        "vpn", "ping", "firewall", "bandwidth", "router", "ethernet",
        "ip address", "no internet", "slow internet", "latency", "packet"
    ],
    "Login": [
        "login", "password", "forgot password", "reset password",
        "account locked", "cannot log in", "sign in", "authentication",
        "two-factor", "2fa", "otp", "access denied", "credentials",
        "username", "session expired", "locked out"
    ],
    "Software": [
        "software", "application", "app", "crash", "error", "install",
        "uninstall", "update", "upgrade", "bug", "freeze", "not responding",
        "blue screen", "bsod", "driver", "license", "activation", "virus",
        "malware", "antivirus", "windows", "macos", "linux", "python",
        "excel", "word", "office", "browser"
    ],
    "Hardware": [
        "hardware", "keyboard", "mouse", "monitor", "screen", "printer",
        "laptop", "desktop", "cpu", "ram", "memory", "hard drive", "ssd",
        "usb", "port", "cable", "display", "battery", "charger",
        "overheating", "fan", "speaker", "headphone", "webcam", "projector"
    ],
}

# Predefined solutions per category
SOLUTIONS = {
    "Network": (
        "  1. Restart your router/modem (unplug 30 sec, replug).\n"
        "  2. Run: ipconfig /release  then  ipconfig /renew\n"
        "  3. Flush DNS: ipconfig /flushdns\n"
        "  4. Check if issue is device-specific or affects all devices.\n"
        "  5. Disable VPN temporarily and retest.\n"
        "  6. Contact your ISP if the problem persists."
    ),
    "Login": (
        "  1. Use 'Forgot Password' link to trigger a reset email.\n"
        "  2. Check Caps Lock is OFF when entering credentials.\n"
        "  3. Clear browser cookies & cache (Ctrl+Shift+Delete).\n"
        "  4. Try incognito/private browser window.\n"
        "  5. If account is locked, wait 15 min or contact IT Admin.\n"
        "  6. Ensure 2FA app time is synced (Google Authenticator settings)."
    ),
    "Software": (
        "  1. Restart the application and try again.\n"
        "  2. Run as Administrator (right-click → Run as Admin).\n"
        "  3. Check for pending updates and install them.\n"
        "  4. Uninstall then reinstall the application cleanly.\n"
        "  5. Check Event Viewer (eventvwr.msc) for error logs.\n"
        "  6. Temporarily disable antivirus to check for conflicts."
    ),
    "Hardware": (
        "  1. Check all cable connections are firmly seated.\n"
        "  2. Test hardware on another machine to isolate the fault.\n"
        "  3. Update or reinstall device driver via Device Manager.\n"
        "  4. Run Windows Hardware Diagnostics.\n"
        "  5. If overheating, clean vents and improve airflow.\n"
        "  6. Log a hardware replacement request if issue persists."
    ),
    "Other": (
        "  1. Your ticket has been logged and assigned to support staff.\n"
        "  2. A technician will review within 24 business hours.\n"
        "  3. For urgent issues, call the helpdesk hotline directly.\n"
        "  4. Provide as much detail as possible for faster resolution."
    ),
}

# Priority keyword lookup (checked top-down; first match wins)
PRIORITY_KEYWORDS = {
    "Critical": ["critical", "urgent", "emergency", "down", "outage",
                 "failure", "not working", "completely", "all users", "production"],
    "High":     ["cannot", "broken", "important", "asap", "high priority",
                 "multiple users", "team", "department"],
    "Medium":   ["slow", "intermittent", "sometimes", "occasional", "degraded"],
}

# Visual decorators
CATEGORY_ICONS = {
    "Network": "🌐", "Login": "🔑",
    "Software": "💻", "Hardware": "🔧", "Other": "📋"
}

PRIORITY_COLORS = {
    "Critical": "bold red",
    "High":     "bold yellow",
    "Medium":   "bold cyan",
    "Low":      "dim",
}

PRIORITY_ICONS = {
    "Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"
}


def classify_query(query: str) -> tuple:
    """
    Classifies query into (category, priority) using keyword scoring.

    Category: count keyword hits per category; pick the highest scorer.
    Priority: scan urgency keywords Critical → High → Medium; default Low.
    """
    text = query.lower()

    # ── Category scoring ──
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[cat] += 1

    best = max(scores, key=scores.get)
    category = best if scores[best] > 0 else "Other"

    # ── Priority scoring ──
    priority = "Low"
    for level, keywords in PRIORITY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            priority = level
            break

    return category, priority


def generate_ticket_id() -> str:
    """Returns a unique ticket ID like TKT-A3F92C1D."""
    return "TKT-" + uuid.uuid4().hex[:8].upper()


# ─────────────────────────────────────────────────────────────────
# 3. RICH CONSOLE HELPERS
# ─────────────────────────────────────────────────────────────────

console = Console() if RICH else None


def cprint(text, style=""):
    """Print with Rich style, or plain if Rich unavailable."""
    if RICH:
        console.print(text, style=style)
    else:
        # Strip Rich markup tags for plain output
        import re
        plain = re.sub(r'\[.*?\]', '', str(text))
        print(plain)


def cinput(prompt_text, default=""):
    """Styled input prompt."""
    if RICH:
        return Prompt.ask(f"[bold cyan]{prompt_text}[/]", default=default)
    else:
        val = input(f"{prompt_text}: ").strip()
        return val if val else default


def cconfirm(prompt_text):
    """Yes/No confirmation prompt."""
    if RICH:
        return Confirm.ask(f"[bold yellow]{prompt_text}[/]")
    else:
        ans = input(f"{prompt_text} [y/N]: ").strip().lower()
        return ans == "y"


def print_header():
    """Prints the app header banner."""
    if RICH:
        console.print()
        console.print(Panel.fit(
            "[bold cyan]🤖  AUTOMATED HELPDESK REASONER[/]\n"
            "[dim]B.Tech AI/Data Science Project  •  Terminal Edition[/]",
            border_style="cyan",
            padding=(0, 4),
        ))
        console.print()
    else:
        print("\n" + "="*60)
        print("   AUTOMATED HELPDESK REASONER — Terminal Edition")
        print("="*60 + "\n")


def print_rule(title=""):
    if RICH:
        console.print(Rule(f"[bold dim]{title}[/]", style="dim"))
    else:
        print(f"\n── {title} " + "─" * max(0, 50 - len(title)))


def print_success(msg):
    cprint(f"\n  ✅  {msg}", "bold green")


def print_error(msg):
    cprint(f"\n  ❌  {msg}", "bold red")


def print_info(msg):
    cprint(f"\n  ℹ️   {msg}", "dim")


# ─────────────────────────────────────────────────────────────────
# 4. FEATURE: SUBMIT A TICKET
# ─────────────────────────────────────────────────────────────────

def submit_ticket():
    """
    Interactive ticket submission flow:
      1. Collect name, email, query
      2. Classify automatically
      3. Display result summary
      4. Save to SQLite
    """
    print_rule("NEW SUPPORT TICKET")
    cprint("\n  Fill in the details below. Type [bold]cancel[/] to go back.\n")

    # ── Collect input ──
    name = cinput("  Your full name")
    if name.lower() == "cancel":
        return

    email = cinput("  Your email address")
    if email.lower() == "cancel":
        return

    cprint("\n  [dim]Describe your issue in detail. Keywords help the AI classify accurately.[/]")
    query = cinput("  Issue description")
    if query.lower() == "cancel":
        return

    # ── Validate ──
    if len(name) < 2 or len(email) < 5 or len(query) < 10:
        print_error("All fields are required. Issue must be at least 10 characters.")
        return

    # ── Classify ──
    category, priority = classify_query(query)
    solution  = SOLUTIONS[category]
    ticket_id = generate_ticket_id()
    created   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Save to DB ──
    conn = get_connection()
    conn.execute(
        """INSERT INTO tickets
           (ticket_id, name, email, query, category, priority, solution, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'Open', ?)""",
        (ticket_id, name, email, query, category, priority, solution, created)
    )
    conn.commit()
    conn.close()

    # ── Display result ──
    print_rule("TICKET CREATED")

    if RICH:
        console.print()
        # Ticket ID panel
        console.print(Panel(
            f"[bold cyan]{ticket_id}[/]",
            title="[dim]Ticket ID[/]",
            border_style="cyan",
            expand=False,
            padding=(0, 3),
        ))
        console.print()

        # Meta info
        meta = Table(box=box.SIMPLE, show_header=False, padding=(0,1))
        meta.add_column(style="dim", width=14)
        meta.add_column()
        meta.add_row("Name",     f"[bold]{name}[/]")
        meta.add_row("Email",    f"[dim]{email}[/]")
        meta.add_row("Category", f"{CATEGORY_ICONS.get(category,'')} [bold]{category}[/]")
        meta.add_row("Priority", f"{PRIORITY_ICONS.get(priority,'')} [{PRIORITY_COLORS.get(priority,'white')}]{priority}[/]")
        meta.add_row("Status",   "[bold yellow]● Open[/]")
        meta.add_row("Created",  f"[dim]{created}[/]")
        console.print(meta)

        # Query
        console.print(Panel(
            f"[dim]{query}[/]",
            title="[dim]Your Query[/]",
            border_style="dim",
        ))

        # Solution
        console.print(Panel(
            solution,
            title=f"[bold cyan]💡 Suggested Solution — {category}[/]",
            border_style="cyan",
        ))

    else:
        print(f"\n  Ticket ID : {ticket_id}")
        print(f"  Category  : {category}")
        print(f"  Priority  : {priority}")
        print(f"  Status    : Open")
        print(f"  Created   : {created}")
        print(f"\n--- Your Query ---\n{query}")
        print(f"\n--- Suggested Solution ({category}) ---\n{solution}")

    print_success("Ticket saved successfully!")
    input("\n  Press Enter to return to main menu...")


# ─────────────────────────────────────────────────────────────────
# 5. FEATURE: VIEW ALL TICKETS
# ─────────────────────────────────────────────────────────────────

def view_tickets(filter_category="All", filter_priority="All", filter_status="All"):
    """
    Displays all tickets in a formatted table with optional filters.
    Filters are applied as SQL WHERE clauses for efficiency.
    """
    print_rule("ALL TICKETS")

    conn   = get_connection()
    query  = "SELECT * FROM tickets WHERE 1=1"
    params = []

    if filter_category != "All":
        query += " AND category = ?";  params.append(filter_category)
    if filter_priority != "All":
        query += " AND priority = ?";  params.append(filter_priority)
    if filter_status != "All":
        query += " AND status = ?";    params.append(filter_status)

    query  += " ORDER BY id DESC"
    rows    = conn.execute(query, params).fetchall()

    # Summary stats (always from full table)
    all_rows = conn.execute("SELECT priority, status FROM tickets").fetchall()
    conn.close()

    total    = len(all_rows)
    open_n   = sum(1 for r in all_rows if r["status"] == "Open")
    resolved = sum(1 for r in all_rows if r["status"] == "Resolved")
    critical = sum(1 for r in all_rows if r["priority"] == "Critical")

    if RICH:
        # Stats bar
        console.print()
        stats_text = (
            f"[dim]Total:[/] [bold cyan]{total}[/]   "
            f"[dim]Open:[/] [bold yellow]{open_n}[/]   "
            f"[dim]Resolved:[/] [bold green]{resolved}[/]   "
            f"[dim]Critical:[/] [bold red]{critical}[/]"
        )
        if filter_category != "All" or filter_priority != "All" or filter_status != "All":
            active = []
            if filter_category != "All": active.append(f"category={filter_category}")
            if filter_priority != "All": active.append(f"priority={filter_priority}")
            if filter_status   != "All": active.append(f"status={filter_status}")
            stats_text += f"   [dim]│ Filter: {', '.join(active)}[/]"
        console.print(f"  {stats_text}\n")

        if not rows:
            console.print("  [dim]No tickets found matching the current filters.[/]\n")
            input("  Press Enter to return...")
            return

        # Table
        tbl = Table(
            box=box.ROUNDED,
            border_style="dim",
            header_style="bold dim",
            show_lines=True,
        )
        tbl.add_column("Ticket ID",  style="cyan",  no_wrap=True)
        tbl.add_column("Name",       style="bold",  max_width=18)
        tbl.add_column("Category",   no_wrap=True)
        tbl.add_column("Priority",   no_wrap=True)
        tbl.add_column("Status",     no_wrap=True)
        tbl.add_column("Created",    style="dim",   no_wrap=True)
        tbl.add_column("Query Preview", max_width=35)

        for r in rows:
            # Category cell
            cat_color = {"Network":"bright_blue","Login":"magenta",
                         "Software":"bright_green","Hardware":"bright_yellow"}.get(r["category"],"white")
            cat_cell  = f"{CATEGORY_ICONS.get(r['category'],'')} [{cat_color}]{r['category']}[/]"

            # Priority cell
            pri_cell  = f"{PRIORITY_ICONS.get(r['priority'],'')} [{PRIORITY_COLORS.get(r['priority'],'white')}]{r['priority']}[/]"

            # Status cell
            status_cell = "[bold yellow]● Open[/]" if r["status"] == "Open" else "[bold green]✓ Resolved[/]"

            # Query preview (first 60 chars)
            preview = r["query"][:60] + ("…" if len(r["query"]) > 60 else "")

            tbl.add_row(
                r["ticket_id"],
                r["name"],
                cat_cell,
                pri_cell,
                status_cell,
                r["created_at"][:10],
                f"[dim]{preview}[/]",
            )

        console.print(tbl)

    else:
        print(f"\n  Stats — Total:{total}  Open:{open_n}  Resolved:{resolved}  Critical:{critical}\n")
        if not rows:
            print("  No tickets found.")
            input("  Press Enter to return...")
            return

        fmt = "  {:<16} {:<16} {:<10} {:<10} {:<10}  {}"
        print(fmt.format("TICKET ID", "NAME", "CATEGORY", "PRIORITY", "STATUS", "QUERY PREVIEW"))
        print("  " + "-"*90)
        for r in rows:
            preview = r["query"][:35] + ("…" if len(r["query"]) > 35 else "")
            print(fmt.format(
                r["ticket_id"], r["name"][:16],
                r["category"], r["priority"], r["status"], preview
            ))

    input("\n  Press Enter to return to main menu...")


# ─────────────────────────────────────────────────────────────────
# 6. FEATURE: FILTER TICKETS
# ─────────────────────────────────────────────────────────────────

def filter_tickets_menu():
    """Prompts for filter options then calls view_tickets."""
    print_rule("FILTER TICKETS")
    cprint("\n  Leave blank (press Enter) to skip a filter.\n")

    cat_options = ["Network", "Login", "Software", "Hardware", "Other"]
    pri_options = ["Critical", "High", "Medium", "Low"]

    if RICH:
        cprint("  [dim]Categories:[/] " + "  ".join(
            [f"[bold]{i+1}[/]. {c}" for i, c in enumerate(cat_options)]
        ) + "  [bold]0[/]. All")
        cat_choice = cinput("  Category number", "0")
        try:
            filter_cat = cat_options[int(cat_choice)-1] if cat_choice != "0" else "All"
        except (ValueError, IndexError):
            filter_cat = "All"

        cprint("\n  [dim]Priorities:[/] " + "  ".join(
            [f"[bold]{i+1}[/]. {p}" for i, p in enumerate(pri_options)]
        ) + "  [bold]0[/]. All")
        pri_choice = cinput("  Priority number", "0")
        try:
            filter_pri = pri_options[int(pri_choice)-1] if pri_choice != "0" else "All"
        except (ValueError, IndexError):
            filter_pri = "All"

        cprint("\n  [dim]Status:[/]  [bold]1[/]. Open  [bold]2[/]. Resolved  [bold]0[/]. All")
        st_choice = cinput("  Status number", "0")
        filter_st = {"1": "Open", "2": "Resolved"}.get(st_choice, "All")

    else:
        print("  Categories: " + " | ".join([f"{i+1}.{c}" for i,c in enumerate(cat_options)]) + " | 0.All")
        cat_choice = input("  Category [0]: ").strip() or "0"
        try:
            filter_cat = cat_options[int(cat_choice)-1] if cat_choice != "0" else "All"
        except (ValueError, IndexError):
            filter_cat = "All"

        print("  Priorities: " + " | ".join([f"{i+1}.{p}" for i,p in enumerate(pri_options)]) + " | 0.All")
        pri_choice = input("  Priority [0]: ").strip() or "0"
        try:
            filter_pri = pri_options[int(pri_choice)-1] if pri_choice != "0" else "All"
        except (ValueError, IndexError):
            filter_pri = "All"

        print("  Status: 1.Open | 2.Resolved | 0.All")
        st_choice = input("  Status [0]: ").strip() or "0"
        filter_st = {"1": "Open", "2": "Resolved"}.get(st_choice, "All")

    view_tickets(filter_cat, filter_pri, filter_st)


# ─────────────────────────────────────────────────────────────────
# 7. FEATURE: VIEW TICKET DETAIL
# ─────────────────────────────────────────────────────────────────

def view_ticket_detail():
    """Looks up a single ticket by ID and shows full details + solution."""
    print_rule("VIEW TICKET DETAILS")
    ticket_id = cinput("\n  Enter Ticket ID (e.g. TKT-A1B2C3D4)").upper().strip()

    conn   = get_connection()
    ticket = conn.execute(
        "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()
    conn.close()

    if not ticket:
        print_error(f"No ticket found with ID: {ticket_id}")
        input("\n  Press Enter to return...")
        return

    print_rule(ticket_id)

    if RICH:
        console.print()
        meta = Table(box=box.SIMPLE, show_header=False, padding=(0,2))
        meta.add_column(style="dim", width=14)
        meta.add_column()
        meta.add_row("Ticket ID",  f"[bold cyan]{ticket['ticket_id']}[/]")
        meta.add_row("Name",       f"[bold]{ticket['name']}[/]")
        meta.add_row("Email",      f"[dim]{ticket['email']}[/]")
        meta.add_row("Category",
            f"{CATEGORY_ICONS.get(ticket['category'],'')} [bold]{ticket['category']}[/]")
        meta.add_row("Priority",
            f"{PRIORITY_ICONS.get(ticket['priority'],'')} [{PRIORITY_COLORS.get(ticket['priority'],'white')}]{ticket['priority']}[/]")
        meta.add_row("Status",
            "[bold yellow]● Open[/]" if ticket['status'] == "Open" else "[bold green]✓ Resolved[/]")
        meta.add_row("Created",    f"[dim]{ticket['created_at']}[/]")
        console.print(meta)

        console.print(Panel(ticket['query'],   title="[dim]Query[/]",    border_style="dim"))
        console.print(Panel(ticket['solution'], title=f"[bold cyan]💡 Solution — {ticket['category']}[/]", border_style="cyan"))
    else:
        t = ticket
        print(f"\n  Ticket ID : {t['ticket_id']}")
        print(f"  Name      : {t['name']}")
        print(f"  Email     : {t['email']}")
        print(f"  Category  : {t['category']}")
        print(f"  Priority  : {t['priority']}")
        print(f"  Status    : {t['status']}")
        print(f"  Created   : {t['created_at']}")
        print(f"\n--- Query ---\n{t['query']}")
        print(f"\n--- Solution ({t['category']}) ---\n{t['solution']}")

    input("\n  Press Enter to return to main menu...")


# ─────────────────────────────────────────────────────────────────
# 8. FEATURE: RESOLVE A TICKET
# ─────────────────────────────────────────────────────────────────

def resolve_ticket():
    """Marks an Open ticket as Resolved."""
    print_rule("RESOLVE TICKET")
    ticket_id = cinput("\n  Enter Ticket ID to resolve").upper().strip()

    conn   = get_connection()
    ticket = conn.execute(
        "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()

    if not ticket:
        print_error(f"Ticket {ticket_id} not found.")
        conn.close()
        input("\n  Press Enter to return...")
        return

    if ticket["status"] == "Resolved":
        print_info(f"Ticket {ticket_id} is already Resolved.")
        conn.close()
        input("\n  Press Enter to return...")
        return

    cprint(f"\n  [dim]Ticket:[/] {ticket_id}  [dim]|[/]  {ticket['name']}  [dim]|[/]  {ticket['category']}")

    if cconfirm("  Mark this ticket as Resolved?"):
        conn.execute(
            "UPDATE tickets SET status = 'Resolved' WHERE ticket_id = ?", (ticket_id,)
        )
        conn.commit()
        print_success(f"Ticket {ticket_id} marked as Resolved.")
    else:
        print_info("Action cancelled.")

    conn.close()
    input("\n  Press Enter to return to main menu...")


# ─────────────────────────────────────────────────────────────────
# 9. FEATURE: DELETE A TICKET
# ─────────────────────────────────────────────────────────────────

def delete_ticket():
    """Permanently deletes a ticket after confirmation."""
    print_rule("DELETE TICKET")
    ticket_id = cinput("\n  Enter Ticket ID to delete").upper().strip()

    conn   = get_connection()
    ticket = conn.execute(
        "SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)
    ).fetchone()

    if not ticket:
        print_error(f"Ticket {ticket_id} not found.")
        conn.close()
        input("\n  Press Enter to return...")
        return

    cprint(f"\n  [bold red]WARNING:[/] This will permanently delete ticket {ticket_id}.")
    cprint(f"  [dim]Reporter:[/] {ticket['name']}  [dim]|[/]  {ticket['query'][:60]}…")

    if cconfirm("  Confirm permanent deletion?"):
        conn.execute("DELETE FROM tickets WHERE ticket_id = ?", (ticket_id,))
        conn.commit()
        print_success(f"Ticket {ticket_id} deleted.")
    else:
        print_info("Deletion cancelled.")

    conn.close()
    input("\n  Press Enter to return to main menu...")


# ─────────────────────────────────────────────────────────────────
# 10. MAIN MENU
# ─────────────────────────────────────────────────────────────────

MENU_OPTIONS = [
    ("1", "📝  Submit a new support ticket"),
    ("2", "📋  View all tickets"),
    ("3", "🔍  Filter tickets"),
    ("4", "🎫  View ticket detail"),
    ("5", "✅  Resolve a ticket"),
    ("6", "🗑️   Delete a ticket"),
    ("0", "🚪  Exit"),
]


def print_menu():
    """Renders the main menu."""
    if RICH:
        console.print()
        tbl = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        tbl.add_column(style="bold cyan", width=5)
        tbl.add_column()
        for key, label in MENU_OPTIONS:
            tbl.add_row(f"[{key}]", label)
        console.print(tbl)
        console.print()
    else:
        print()
        for key, label in MENU_OPTIONS:
            print(f"  [{key}] {label}")
        print()


def main():
    """Application entry point — initialises DB and runs the menu loop."""
    # Ensure DB is ready
    init_db()

    # Clear screen if possible
    os.system("cls" if os.name == "nt" else "clear")

    print_header()

    if not RICH:
        print("  TIP: Install 'rich' for a better experience:  pip install rich\n")

    while True:
        print_menu()

        choice = cinput("  Select option", "")

        if choice == "1":
            submit_ticket()
        elif choice == "2":
            view_tickets()
        elif choice == "3":
            filter_tickets_menu()
        elif choice == "4":
            view_ticket_detail()
        elif choice == "5":
            resolve_ticket()
        elif choice == "6":
            delete_ticket()
        elif choice == "0":
            cprint("\n  [bold cyan]Goodbye! 👋[/]\n")
            sys.exit(0)
        else:
            print_error("Invalid option. Please enter a number from the menu.")


if __name__ == "__main__":
    main()
