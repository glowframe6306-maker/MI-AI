
(function () {
    "use strict";

    const firebaseConfig = {
        apiKey: "AIzaSyAxrIAKDz0b9GdHp4K_-jBKZWIcWZTww5g",
        authDomain: "mi-ai-99e6a.firebaseapp.com",
        projectId: "mi-ai-99e6a",
        storageBucket: "mi-ai-99e6a.firebasestorage.app",
        messagingSenderId: "845086558623",
        appId: "1:845086558623:web:8ff161f6a157cf87d395aa"
    };

    // ========== FIRESTORE PERSISTENCE MANAGER ==========
    class FirestorePersistenceManager {
        constructor(db) {
            this.db = db;
            this.uid = null;
            this.listeners = [];
        }

        setUser(uid) {
            this.uid = uid;
        }

        unsubscribeAll() {
            this.listeners.forEach(unsubscribe => {
                if (typeof unsubscribe === 'function') {
                    try {
                        unsubscribe();
                    } catch (e) {
                        console.error('Error unsubscribing listener:', e);
                    }
                }
            });
            this.listeners = [];
        }

        async saveSettings(settings) {
            if (!this.uid) return;
            try {
                const docRef = window.firebase.firestore().collection('users').doc(this.uid).collection('settings').doc('general');
                await docRef.set({
                    theme: settings.theme || '',
                    fontSize: settings.fontSize || 15,
                    language: settings.language || 'en',
                    updatedAt: window.firebase.firestore.Timestamp.now()
                }, { merge: true });
                console.log('[Persistence] Settings saved to Firestore');
            } catch (err) {
                console.error('[Persistence] Error saving settings:', err.message);
            }
        }

        async saveChat(chatId, chatData) {
            if (!this.uid) return;
            try {
                const chatRef = window.firebase.firestore().collection('users').doc(this.uid).collection('chats').doc(chatId);
                await chatRef.set({
                    title: chatData.title || 'Chat',
                    pin: chatData.pin || false,
                    createdAt: window.firebase.firestore.Timestamp.now(),
                    updatedAt: window.firebase.firestore.Timestamp.now(),
                    messageCount: chatData.messageCount || 0
                }, { merge: true });
                console.log(`[Persistence] Chat ${chatId} saved to Firestore`);
            } catch (err) {
                console.error('[Persistence] Error saving chat:', err.message);
            }
        }

        async saveMessage(chatId, messageId, message) {
            if (!this.uid) return;
            try {
                const messageRef = window.firebase.firestore().collection('users').doc(this.uid)
                    .collection('chats').doc(chatId)
                    .collection('messages').doc(messageId);
                await messageRef.set({
                    role: message.role || 'user',
                    text: message.text || '',
                    createdAt: window.firebase.firestore.Timestamp.now()
                });
                console.log(`[Persistence] Message ${messageId} saved to Firestore`);
            } catch (err) {
                console.error('[Persistence] Error saving message:', err.message);
            }
        }

        async loadUserData() {
            if (!this.uid) return { chats: {}, settings: {} };
            try {
                const userRef = window.firebase.firestore().collection('users').doc(this.uid);

                // Load settings
                const settingsDoc = await userRef.collection('settings').doc('general').get();
                const settings = settingsDoc.exists ? settingsDoc.data() : {};

                // Load chats and messages
                const chatsSnapshot = await userRef.collection('chats').get();
                const chats = {};

                for (const chatDoc of chatsSnapshot.docs) {
                    const chatId = chatDoc.id;
                    const chatData = chatDoc.data();

                    const messagesSnapshot = await userRef.collection('chats').doc(chatId).collection('messages').get();
                    const messages = messagesSnapshot.docs.map(doc => {
                        const data = doc.data();
                        return {
                            role: data.role === 'ai' ? 'ai' : 'me',
                            text: data.text || ''
                        };
                    });

                    chats[chatId] = messages;
                    chats[chatId].title = chatData.title || chatId;
                    chats[chatId].pin = chatData.pin || false;
                    chats[chatId].messageCount = messages.length;
                }

                console.log('[Persistence] User data loaded from Firestore:', { chats: Object.keys(chats), settings });
                return { chats, settings };
            } catch (err) {
                console.error('[Persistence] Error loading user data:', err.message);
                return { chats: {}, settings: {} };
            }
        }
    }

    window.FirestorePersistenceManager = FirestorePersistenceManager;

    function getFirebaseLanguage() {
        const selected =
            document.getElementById("languageSelect")?.value;

        const stored =
            localStorage.getItem("mi_ui_language");

        const language = selected || stored || "en";

        const languageMap = {
            en: "en",
            si: "si",
            ta: "ta"
        };

        return languageMap[language] || "en";
    }

    function firebaseErrorMessage(error) {
        const errorCode = String(error?.code || "");

        const messages = {
            "auth/invalid-email":
                "Invalid email address.",

            "auth/missing-password":
                "Please enter your password.",

            "auth/weak-password":
                "Password must contain at least 6 characters.",

            "auth/email-already-in-use":
                "An account already exists with this email.",

            "auth/user-not-found":
                "No account was found for this email.",

            "auth/wrong-password":
                "Incorrect email or password.",

            "auth/invalid-credential":
                "Incorrect email or password.",

            "auth/too-many-requests":
                "Too many attempts. Please try again later.",

            "auth/network-request-failed":
                "Network error. Check your internet connection.",

            "auth/operation-not-allowed":
                "Email and password login is not enabled in Firebase.",

            "auth/unauthorized-domain":
                "This website domain is not authorized in Firebase."
        };

        return (
            messages[errorCode] ||
            error?.message ||
            "Firebase authentication failed."
        );
    }

    function initializeMIFirebase() {
        if (typeof window.firebase === "undefined") {
            throw new Error("Firebase SDK failed to load.");
        }

        let app;

        if (
            Array.isArray(window.firebase.apps) &&
            window.firebase.apps.length > 0
        ) {
            app = window.firebase.app();
        }
        else {
            app = window.firebase.initializeApp(
                firebaseConfig
            );
        }

        const auth = window.firebase.auth(app);
        const db = window.firebase.firestore(app);

        auth.languageCode = getFirebaseLanguage();

        window.miFirebaseApp = app;
        window.miFirebaseAuth = auth;
        window.miFirebaseDb = db;
        window.miFirebaseUser = auth.currentUser || null;

        // Initialize persistence manager
        window.firestorePersistence = new window.FirestorePersistenceManager(db);

        auth.onAuthStateChanged(function (user) {
            window.miFirebaseUser = user || null;

            // Update persistence manager with current user
            if (user) {
                window.firestorePersistence.setUser(user.uid);
                console.log('[Persistence] Auth user set:', user.uid);
            } else {
                window.firestorePersistence.setUser(null);
                console.log('[Persistence] Auth user cleared');
            }

            window.dispatchEvent(
                new CustomEvent(
                    "mi-firebase-auth-changed",
                    {
                        detail: {
                            user: user || null
                        }
                    }
                )
            );
        });

        window.MIFirebase = {
            config: Object.freeze({
                ...firebaseConfig
            }),

            get auth() {
                return window.miFirebaseAuth;
            },

            get user() {
                return (
                    window.miFirebaseAuth?.currentUser ||
                    null
                );
            },

            updateLanguage: function () {
                if (window.miFirebaseAuth) {
                    window.miFirebaseAuth.languageCode =
                        getFirebaseLanguage();
                }
            },

            register: async function (
                email,
                password,
                profile = {}
            ) {
                try {
                    this.updateLanguage();

                    const credential =
                        await auth
                            .createUserWithEmailAndPassword(
                                String(email || "").trim(),
                                String(password || "")
                            );

                    const user = credential.user;

                    const displayName = String(
                        profile.displayName ||
                        profile.fullName ||
                        profile.name ||
                        ""
                    ).trim();

                    if (displayName) {
                        await user.updateProfile({
                            displayName: displayName
                        });
                    }

                    await user.sendEmailVerification({
                        url: window.location.origin
                    });

                    return user;
                }
                catch (error) {
                    console.error(
                        "[CORTEX CORE AI Firebase register]",
                        error
                    );

                    throw new Error(
                        firebaseErrorMessage(error)
                    );
                }
            },

            login: async function (
                email,
                password
            ) {
                try {
                    this.updateLanguage();

                    const credential =
                        await auth
                            .signInWithEmailAndPassword(
                                String(email || "").trim(),
                                String(password || "")
                            );

                    return credential.user;
                }
                catch (error) {
                    console.error(
                        "[CORTEX CORE AI Firebase login]",
                        error
                    );

                    throw new Error(
                        firebaseErrorMessage(error)
                    );
                }
            },

            sendPasswordResetEmail:
                async function (email) {
                    try {
                        this.updateLanguage();

                        await auth.sendPasswordResetEmail(
                            String(email || "").trim(),
                            {
                                url: window.location.origin
                            }
                        );

                        return true;
                    }
                    catch (error) {
                        console.error(
                            "[CORTEX CORE AI Firebase reset]",
                            error
                        );

                        throw new Error(
                            firebaseErrorMessage(error)
                        );
                    }
                },

            resendVerification:
                async function () {
                    try {
                        this.updateLanguage();

                        const user =
                            auth.currentUser;

                        if (!user) {
                            throw new Error(
                                "Please sign in first."
                            );
                        }

                        await user.sendEmailVerification({
                            url: window.location.origin
                        });

                        return true;
                    }
                    catch (error) {
                        throw new Error(
                            firebaseErrorMessage(error)
                        );
                    }
                },

            logout: async function () {
                await auth.signOut();
                return true;
            }
        };

        document.addEventListener(
            "change",
            function (event) {
                if (
                    event.target &&
                    event.target.id ===
                        "languageSelect"
                ) {
                    window.MIFirebase.updateLanguage();
                }
            }
        );

        console.log(
            "[CORTEX CORE AI] Firebase Authentication connected:",
            firebaseConfig.projectId
        );

        window.dispatchEvent(
            new CustomEvent("mi-firebase-ready")
        );
    }

    function startFirebase() {
        try {
            initializeMIFirebase();
        }
        catch (error) {
            console.error(
                "[CORTEX CORE AI] Firebase initialization failed:",
                error
            );

            window.dispatchEvent(
                new CustomEvent(
                    "mi-firebase-error",
                    {
                        detail: {
                            message: error.message
                        }
                    }
                )
            );
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener(
            "DOMContentLoaded",
            startFirebase,
            {
                once: true
            }
        );
    }
    else {
        startFirebase();
    }
})();
