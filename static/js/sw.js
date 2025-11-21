const CACHE_NAME = 'cookie-craze-v1.0';
const urlsToCache = [
    '/',
    '/static/css/style.css',
    '/static/images/cookie-craze-logo.png',
    '/static/js/app.js',
    '/inventory/',
    '/offline/'
];

// Install event - cache essential files
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                return cache.addAll(urlsToCache);
            })
    );
});

// Fetch event - serve from cache if available
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                // Return cached version or fetch from network
                return response || fetch(event.request);
            })
    );
});