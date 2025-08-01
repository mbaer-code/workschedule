// src/static/js/signup.js

// Check if Firebase is initialized and ready to use
document.addEventListener('DOMContentLoaded', function() {
    if (firebase.apps.length === 0) {
        console.error("Firebase has not been initialized. Check firebase_init.js.");
        return;
    }

    // Get a reference to the signup form
    const signupForm = document.getElementById('signup-form');

    signupForm.addEventListener('submit', async (event) => {
        // Prevent the default form submission behavior
        event.preventDefault();

        // Get the values from the form inputs
        const email = signupForm.querySelector('#email').value;
        const password = signupForm.querySelector('#password').value;
        const confirmPassword = signupForm.querySelector('#confirm-password').value;

        // Simple validation to ensure passwords match
        if (password !== confirmPassword) {
            alert("Passwords do not match. Please try again.");
            return;
        }

        try {
            // Use Firebase to create a new user with email and password
            const userCredential = await firebase.auth().createUserWithEmailAndPassword(email, password);
            console.log("User created successfully:", userCredential.user);

            // Redirect the user to the schedule upload page upon successful signup
            window.location.href = '/schedule/upload';

        } catch (error) {
            // Handle specific Firebase authentication errors and display them to the user
            let errorMessage = "An unexpected error occurred. Please try again.";

            switch (error.code) {
                case 'auth/email-already-in-use':
                    errorMessage = 'This email address is already in use by another account.';
                    break;
                case 'auth/invalid-email':
                    errorMessage = 'The email address you provided is not valid.';
                    break;
                case 'auth/weak-password':
                    errorMessage = 'The password is too weak. Please choose a stronger one.';
                    break;
                default:
                    console.error("Firebase Auth Error:", error.code, error.message);
                    break;
            }
            alert(errorMessage);
        }
    });
});

