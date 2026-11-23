# ddos_tool

HTTP flood / stress test với TLS impersonation bypass Cloudflare JS challenge.

## Cảnh báo

Dùng cho **stress test hệ thống của chính bạn** hoặc môi trường được cấp phép. Flood vào hệ thống của người khác là hành vi vi phạm pháp luật Việt Nam (Điều 287 BLHS) và luật pháp hầu hết các nước.

## Yêu cầu

- Python 3.10+
- Proxy list (file `host:port/line` hoặc scrape từ list public)

## Cài đặt

```bash
cd ddos_tool
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt