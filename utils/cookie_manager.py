def load_cookie_string(filepath):
    """从文件读取 Netscape 格式 cookie 字符串"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Error reading cookie file: {e}")
        return ""