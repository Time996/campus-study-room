from studyroom import create_app

app = create_app()

if __name__ == '__main__':
    # Local classroom development only. The reloader is disabled to avoid two processes.
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
