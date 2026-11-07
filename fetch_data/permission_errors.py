"""Recognize permanent interface authorization failures, not rate limits."""
SKIP_EXIT_CODE = 3


def is_permission_denied(error):
    message = str(error).lower()
    return any(text in message for text in (
        '40203', '没有接口', '无接口权限', '没有访问该接口的权限',
        '无权访问该接口', '没有权限访问', '接口权限不足',
    ))


def skip_if_permission_denied(error, interface):
    if is_permission_denied(error):
        print(f'[SKIP] {interface}：无接口权限，跳过此类数据。', flush=True)
        raise SystemExit(SKIP_EXIT_CODE)
