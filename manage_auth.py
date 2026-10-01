"""أداة إدارة المستخدمين والمفاتيح."""
import sys
from src.auth import (
    init_db, create_user, create_api_key,
)

def main():
    init_db()
    if len(sys.argv) < 2:
        print("""
الاستخدام:
  python manage_auth.py create-user <username> <password> [role]
  python manage_auth.py create-key <name> [role]
        """)
        return

    cmd = sys.argv[1]
    if cmd == "create-user":
        if len(sys.argv) < 4:
            print("خطأ: username و password مطلوبان")
            return
        role = sys.argv[4] if len(sys.argv) > 4 else "user"
        create_user(sys.argv[2], sys.argv[3], role)
        print(f"✅ تم إنشاء المستخدم: {sys.argv[2]} (role={role})")

    elif cmd == "create-key":
        if len(sys.argv) < 3:
            print("خطأ: name مطلوب")
            return
        role = sys.argv[4] if len(sys.argv) > 4 else "user"
        key = create_api_key(sys.argv[2], role)
        print(f"🔑 المفتاح الجديد (احفظه الآن، لن يظهر مجددًا):\n{key}")


if __name__ == "__main__":
    main()
