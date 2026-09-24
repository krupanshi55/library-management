from app import create_app

app = create_app()

# Auto-seed the database on startup (safe — skips if data already exists)
with app.app_context():
    try:
        from app.models import User
        if not User.query.first():
            print("[SEED] No users found. Running seed...")
            from seed import seed
            seed()
            print("[SEED] Done.")
        else:
            print("[SEED] Database already seeded. Skipping.")
    except Exception as e:
        print(f"[SEED] Error during seeding: {e}")

if __name__ == "__main__":
    app.run()
