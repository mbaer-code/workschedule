// workschedule-cloud/src/static/js/firebase_auth.js

// 1. Your Firebase Project Configuration (PASTE YOURS HERE)
const firebaseConfig = {
  apiKey: "AIzaSyBIGGseFMifZwPk6RFuqs2ID7bKKASKF0w", // <--- Make sure this is YOUR actual API key
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
            // Create user with email and password
            const userCredential = await auth.createUserWithEmailAndPassword(email, password);
            console.log('User signed up:', userCredential.user.email, userCredential.user.uid);
            showMessage('Sign up successful! Redirecting to login...', false);

            // Redirect after a short delay for message visibility
            setTimeout(() => {
                window.location.href = '/login'; // Redirect to login page
            }, 1500); // 1.5 second delay

        } catch (error) {
            console.error('Sign up error:', error.message);
            // Display Firebase-specific error messages
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
            // Sign in user with email and password
            const userCredential = await auth.signInWithEmailAndPassword(email, password);
            console.log('User logged in:', userCredential.user.email, userCredential.user.uid);
            showMessage('Login successful! Redirecting...', false);

            // Redirect after a short delay for message visibility
            setTimeout(() => {
                window.location.href = '/dashboard'; // Redirect to a dashboard/home page (next step!)
            }, 1500); // 1.5 second delay

        } catch (error) {
            console.error('Login error:', error.message);
            // Display Firebase-specific error messages
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

// --- Basic Auth State Observer (Good practice for tracking user status) ---
auth.onAuthStateChanged((user) => {
    if (user) {
        // User is signed in.
        console.log("Auth state changed: User is signed in:", user.email, user.uid);
        // You might want to redirect authenticated users away from login/signup pages
        // if they try to access them directly while already logged in.
        // if (window.location.pathname === '/' || window.location.pathname === '/login' || window.location.pathname === '/signup') {
        //      // window.location.href = '/dashboard'; // Uncomment if you want immediate redirect
        // }
    } else {
        // User is signed out.
        console.log("Auth state changed: User is signed out.");
        // If they are on a protected page and logged out, you might redirect them to login.
        // if (window.location.pathname === '/dashboard') { // Example: If on dashboard, redirect to login
        //     // window.location.href = '/login';
        // }
    }
});
