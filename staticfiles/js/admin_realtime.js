// Real-time functionality for admin order management
class AdminRealtime {
    constructor() {
        this.lastCheck = null;
        this.newOrdersCount = 0;
        this.init();
    }

    init() {
        this.setupRealTimeUpdates();
        this.setupOrderNotifications();
    }

    setupRealTimeUpdates() {
        // Check for new orders every 15 seconds
        setInterval(() => {
            this.checkNewOrders();
            this.refreshOrders();
        }, 15000);
    }

    async checkNewOrders() {
        try {
            const params = this.lastCheck ? `?last_check=${this.lastCheck}` : '';
            const response = await fetch(`/api/new-orders-count/${params}`);
            const data = await response.json();
            
            if (data.new_orders_count > this.newOrdersCount) {
                this.showNewOrderNotification(data.new_orders_count);
            }
            
            this.newOrdersCount = data.new_orders_count;
            this.lastCheck = data.current_time;
        } catch (error) {
            console.error('Error checking new orders:', error);
        }
    }

    async refreshOrders() {
        try {
            const response = await fetch('/api/todays-orders/');
            const data = await response.json();
            
            // Update the orders table
            this.updateOrdersTable(data.orders);
        } catch (error) {
            console.error('Error refreshing orders:', error);
        }
    }

    updateOrdersTable(orders) {
        // This would typically update the orders table via AJAX
        // For now, we'll just reload the page if there are changes
        const currentOrderCount = document.querySelectorAll('.unified-table tbody tr').length;
        if (orders.length !== currentOrderCount) {
            location.reload();
        }
    }

    showNewOrderNotification(count) {
        // Create a notification badge
        let notificationBadge = document.getElementById('newOrdersBadge');
        if (!notificationBadge) {
            notificationBadge = document.createElement('span');
            notificationBadge.id = 'newOrdersBadge';
            notificationBadge.className = 'badge bg-danger position-absolute top-0 start-100 translate-middle';
            notificationBadge.style.cssText = 'font-size: 0.6rem; padding: 0.25em 0.4em;';
            
            const ordersLink = document.querySelector('a[href*="admin/orders"]');
            if (ordersLink) {
                ordersLink.style.position = 'relative';
                ordersLink.appendChild(notificationBadge);
            }
        }
        
        notificationBadge.textContent = count;
        
        // Show browser notification
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('New Orders!', {
                body: `${count} new customer order${count > 1 ? 's' : ''} received`,
                icon: '/static/images/cookie-craze-logo.png'
            });
        }
        
        // Auto-remove badge after 5 seconds
        setTimeout(() => {
            if (notificationBadge.parentNode) {
                notificationBadge.parentNode.removeChild(notificationBadge);
            }
        }, 5000);
    }

    setupOrderNotifications() {
        if ('Notification' in window) {
            Notification.requestPermission();
        }
    }
}

// Initialize admin real-time features
document.addEventListener('DOMContentLoaded', function() {
    window.adminRealtime = new AdminRealtime();
});