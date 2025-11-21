// Real-time functionality for customer dashboard
class CustomerRealtime {
    constructor() {
        this.lastOrderCheck = null;
        this.init();
    }

    init() {
        this.setupOrderUpdates();
        this.setupNotifications();
    }

    setupOrderUpdates() {
        // Check for order status updates every 30 seconds
        setInterval(() => {
            this.checkOrderUpdates();
        }, 30000);
    }

    async checkOrderUpdates() {
        try {
            const response = await fetch('/api/todays-orders/');
            const data = await response.json();
            
            // Update order statuses on the page
            this.updateOrderStatuses(data.orders);
        } catch (error) {
            console.error('Error checking order updates:', error);
        }
    }

    updateOrderStatuses(orders) {
        // Update order status badges on the page
        orders.forEach(order => {
            const statusElement = document.querySelector(`[data-order-id="${order.id}"] .order-status`);
            if (statusElement) {
                statusElement.className = `order-status status-${order.status}`;
                statusElement.textContent = order.status_display;
            }
        });
    }

    setupNotifications() {
        // Request notification permission
        if ('Notification' in window) {
            Notification.requestPermission();
        }
    }

    showOrderNotification(order) {
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('Order Status Updated', {
                body: `Order ${order.hex_id} is now ${order.status_display}`,
                icon: '/static/images/cookie-craze-logo.png'
            });
        }
    }
}

// Initialize real-time features
document.addEventListener('DOMContentLoaded', function() {
    window.customerRealtime = new CustomerRealtime();
});