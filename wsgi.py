from App import app  # O solo 'App' si está fuera de src/

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
