<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/main.css') }}">
</head>
<body>
    <div class="auth-container">
        <h1 class="auth-title">Welcome to Your Dashboard!</h1>
        <p class="auth-text">You are logged in with User ID: <strong>{{ user_id }}</strong></p>
        <p class="auth-text">This is where you can view your work schedule.</p>
        <a href="{{ url_for('auth_bp.logout') }}" class="auth-link">Logout</a>
    </div>
</body>
</html>



