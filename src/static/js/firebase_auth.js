// workschedule-cloud/src/static/js/firebase_auth.js

// 1. Your Firebase Project Configuration
const firebaseConfig = {
  apiKey: "AIzaSyBIGGseFMifZwPk6RFuqs2ID7bKKASKF0w", 
  authDomain: "work-schedule-cloud-36477.firebaseapp.com",
  projectId: "work-schedule-cloud-36477",
  storageBucket: "work-schedule-cloud-36477.firebasestorage.app",
  messagingSenderId: "746093341275",
  appId: "1:746093341275:web:ec5a54a430991286b16d7e",
  measurementId: "G-EE5YG0J7XP"
};

// Initialize Firebase
const app = firebase.initializeApp(firebaseConfig);
const auth = firebase.auth(); // Get the Auth service instance

// Helper function to display messages on the page
const authMessage = document.getElementById('authMessage');

function showMessage(message, isError = false) {
    if (authMessage) { // Ensure the element with ID 'authMessage' exists
        authMessage.textContent = message;
        authMessage.className = isError ? 'message error' : 'message success';
        setTimeout(() => {
            authMessage.textContent = '';
            authMessage.className = 'message';
        }, 5000); // Clear message after 5 seconds
    } else {
        console.warn("Element with ID 'authMessage' not found. Message couldn't be displayed on page:", message);
    }
}

// Helper to send Firebase ID token to Flask backend to establish server-side session
async function sendTokenToBackend(user, redirectUrl) {
    console.log("sendTokenToBackend: Attempting to send token to Flask."); // NEW LOG
    try {
        const idToken = await user.getIdToken(); // Get the Firebase ID Token
        console.log("sendTokenToBackend: Got ID Token from Firebase user."); // NEW LOG
        
        // Send the ID token to our new Flask endpoint
        const response = await fetch('/authenticate-session', { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // We send the ID token in the Authorization header as a Bearer token
                'Authorization': `Bearer ${idToken}` 
            },
            // No body needed as the token is in the header
            body: JSON.stringify({}) 
        });

        console.log("sendTokenToBackend: Fetch request sent. Checking response..."); // NEW LOG

        if (response.ok) {
            const data = await response.json();
            console.log("sendTokenToBackend: Flask responded with OK. Data:", data); // NEW LOG
            showMessage('Login successful! Redirecting...', false);
            setTimeout(() => {
                window.location.href = redirectUrl; // Redirect after successful session setup
            }, 1000); // 1 second delay
        } else {
            // Handle errors from the Flask backend (e.g., token verification failed)
            const errorData = await response.json();
            console.error("sendTokenToBackend: Flask responded with an error:", response.status, errorData); // NEW LOG
            throw new Error(errorData.error || `Flask backend error: ${response.status}`);
        }
    } catch (error) {
        console.error("sendTokenToBackend: Network or unexpected error during fetch:", error); // NEW LOG
        showMessage(`Error during login/signup: ${error.message}`, true);
    }
}


// --- Sign Up Logic ---
const signupForm = document.getElementById('signupForm');
if (signupForm) { // Only run if signup form exists on the page
    signupForm.addEventListener('submit', async (e) => {
        e.preventDefault(); // Prevent default form submission

        const email = signupForm['signupEmail'].value;
        const password = signupForm['signupPassword'].value;
        const confirmPassword = signupForm['signupConfirmPassword'].value;

        if (password !== confirmPassword) {
            showMessage('Passwords do not match.', true);
            return;
        }

        try {
            // Create user with email and password using Firebase
            const userCredential = await auth.createUserWithEmailAndPassword(email, password);
            console.log('User signed up:', userCredential.user.email, userCredential.user.uid);
            
            // On successful signup, automatically log them in by sending token to backend
            await sendTokenToBackend(userCredential.user, '/dashboard'); 

        } catch (error) {
            console.error('Sign up error:', error.message);
            // Display Firebase-specific error messages to the user
            let errorMessage = "An unknown error occurred during signup.";
            switch (error.code) {
                case 'auth/email-already-in-use':
                    errorMessage = "This email is already in use.";
                    break;
                case 'auth/invalid-email':
                    errorMessage = "Invalid email address.";
                    break;
                case 'auth/operation-not-allowed':
                    errorMessage = "Email/password accounts are not enabled in Firebase project settings. Please enable them.";
                    break;
                case 'auth/weak-password':
                    errorMessage = "Password is too weak. Must be at least 6 characters.";
                    break;
                default:
                    errorMessage = `Error: ${error.message}`;
            }
            showMessage(errorMessage, true);
        }
    });
}

// --- Login Logic ---
const loginForm = document.getElementById('loginForm');
if (loginForm) { // Only run if login form exists on the page
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault(); // Prevent default form submission

        const email = loginForm['loginEmail'].value;
        const password = loginForm['loginPassword'].value;

        try {
            // Sign in user with email and password using Firebase
            const userCredential = await auth.signInWithEmailAndPassword(email, password);
            console.log('User logged in:', userCredential.user.email, userCredential.user.uid);
            
            // On successful login, send token to Flask backend to establish server-side session
            await sendTokenToBackend(userCredential.user, '/dashboard'); 

        } catch (error) {
            console.error('Login error:', error.message);
            // Display Firebase-specific error messages to the user
            let errorMessage = "An unknown error occurred during login.";
            switch (error.code) {
                case 'auth/invalid-email':
                    errorMessage = "Invalid email address.";
                    break;
                case 'auth/user-disabled':
                    errorMessage = "This user account has been disabled.";
                    break;
                case 'auth/user-not-found':
                case 'auth/wrong-password': // Firebase treats incorrect password like user not found for security
                    errorMessage = "Invalid email or password.";
                    break;
                default:
                    errorMessage = `Error: ${error.message}`;
            }
            showMessage(errorMessage, true);
        }
    });
}

// --- Logout Logic ---
const logoutLink = document.getElementById('logoutLink'); // Assumes logout link has this ID
if (logoutLink) {
    logoutLink.addEventListener('click', async (e) => {
        e.preventDefault(); // Prevent default link behavior (don't navigate immediately)

        try {
            await auth.signOut(); // Sign out from Firebase client-side
            
            // Also inform the Flask backend to clear its session via a POST request
            const response = await fetch('/logout', { 
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json' // Even if no body, good practice
                },
                body: JSON.stringify({}) // Send an empty JSON body
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || "Failed to clear server session.");
            }

            console.log("User signed out successfully.");
            showMessage('You have been logged out.', false);
            
            // Redirect to the login page after successful client-side and server-side logout
            setTimeout(() => {
                window.location.href = '/login'; 
            }, 1000); // 1 second delay

        } catch (error) {
            console.error("Logout error:", error.message);
            showMessage(`Logout error: ${error.message}`, true);
        }
    });
}

// --- Basic Auth State Observer (Good practice for tracking user status) ---
// This listener runs whenever the user's sign-in state changes (e.g., login, logout)
auth.onAuthStateChanged((user) => {
    if (user) {
        // User is signed in.
        console.log("Auth state changed: User is signed in.", user.email, user.uid);
        // In a more complex app, you might use this to update UI elements
        // or redirect if they are on auth pages while already logged in.
    } else {
        // User is signed out.
        console.log("Auth state changed: User is signed out.");
        // Similar to above, you could redirect from protected pages if not logged in
        // but our Flask `login_required` decorator handles this for server-rendered pages.
    }
});
