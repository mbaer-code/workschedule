console.log("loading firebase_auth.js... ");

// src/static/js/firebase_auth.js
// This script handles user authentication (signup and login) using Firebase.

import { initializeApp } from "https://www.gstatic.com/firebasejs/9.4.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, createUserWithEmailAndPassword } from "https://www.gstatic.com/firebasejs/9.4.0/firebase-auth.js";

// config
const firebaseConfig = {
  apiKey: "AIzaSyDxV6dx8ni7JwiOHS1cOtnw-AcoOqpdU-k",
  authDomain: "work-schedule-cloud.firebaseapp.com",
  projectId: "work-schedule-cloud",
  storageBucket: "work-schedule-cloud.firebasestorage.app",
  messagingSenderId: "985817149812",
  appId: "1:985817149812:web:93a9079802e681236c7c21",
  measurementId: "G-B34FNHGKEW"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

// Get the form and the message display area
const authForm = document.querySelector('.auth-form');
const messageBox = document.getElementById('messageBox');

// Add a submit event listener to the authentication form
if (authForm) {
    authForm.addEventListener('submit', async (e) => {
        console.log("Form submit intercepted");
        // Prevent the default form submission which would reload the page
        e.preventDefault();

        // Clear any previous messages
        displayMessage('');

        // Get the email and password from the form
        const emailInput = document.getElementById('email');
        const passwordInput = document.getElementById('password');
        const email = emailInput.value;
        const password = passwordInput.value;

        if (!email || !password) {
            displayMessage('Please enter both email and password.');
            return;
        }

        const isLoginPage = authForm.dataset.formType === 'login';

        console.log(`Attempting to submit form. Is login page: ${isLoginPage}`);

        try {
            let userCredential;
            if (isLoginPage) {
                // Handle user login
                console.log('Attempting to sign in with Firebase...');
                userCredential = await signInWithEmailAndPassword(auth, email, password);
                console.log('Firebase sign in successful. User credential:', userCredential);

                displayMessage('Login successful! Redirecting to dashboard...');
                
                // Get the user's ID token and send it to the server
                const idToken = await userCredential.user.getIdToken();
                console.log('ID Token retrieved:', idToken);
                await sendTokenToServer(idToken);
            
                // Redirect to the dashboard on successful session creation
                window.location.href = '/auth/dashboard';

            } else {
                // Handle user signup
                userCredential = await createUserWithEmailAndPassword(auth, email, password);
                displayMessage('Signup successful! Redirecting to login page...');

                // Redirect to the login page after a successful signup
                window.location.href = '/auth/login';
            }

        } catch (error) {
            // Display any Firebase authentication errors to the user
            const errorCode = error.code;
            let errorMessage = error.message;

            if (errorCode === 'auth/wrong-password') {
                errorMessage = 'Incorrect password.';
            } else if (errorCode === 'auth/user-not-found') {
                errorMessage = 'User not found. Please check your email or sign up.';
            } else if (errorCode === 'auth/email-already-in-use') {
                errorMessage = 'This email is already in use. Please log in instead.';
            } else if (errorCode === 'auth/invalid-email') {
                errorMessage = 'The email address is not valid.';
            }
            
            console.error("Firebase Auth Error:", error);
            displayMessage(`Error: ${errorMessage}`);
        }
    });
}

/**
 * Sends the Firebase ID token to the Flask backend to create a session.
 * @param {string} idToken The Firebase ID token.
 */
async function sendTokenToServer(idToken) {
    const response = await fetch('/auth/authenticate-session', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${idToken}`
        }
    });

    if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to authenticate session.');
    }
}

/**
 * Displays a message to the user in a designated message box.
 * @param {string} message The message to display.
 */
function displayMessage(message) {
    if (messageBox) {
        messageBox.textContent = message;
        messageBox.style.display = message ? 'block' : 'none';
    }
}

