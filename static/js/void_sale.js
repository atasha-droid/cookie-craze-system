// Void Sale functionality with admin confirmation
document.addEventListener('DOMContentLoaded', function() {
    console.log('Void sale script loaded');
    
    const voidSaleModal = document.getElementById('voidSaleModal');
    const voidSaleForm = document.getElementById('voidSaleForm');
    const confirmVoidBtn = document.getElementById('confirmVoidBtn');
    
    if (!voidSaleModal || !voidSaleForm || !confirmVoidBtn) {
        console.error('Required elements not found:', {
            voidSaleModal: !!voidSaleModal,
            voidSaleForm: !!voidSaleForm,
            confirmVoidBtn: !!confirmVoidBtn
        });
        return;
    }

    const loadingModal = new bootstrap.Modal(document.getElementById('loadingModal'));
    let currentSaleId = null;

    console.log('Setting up void sale buttons...');

    // Handle void sale button clicks
    document.querySelectorAll('.void-sale-btn').forEach(button => {
        button.addEventListener('click', function(e) {
            console.log('Void button clicked');
            const saleId = this.getAttribute('data-sale-id');
            console.log('Sale ID:', saleId);
            currentSaleId = saleId;
            loadSaleDetails(saleId);
        });
    });

    // Handle reason selection change
    const voidReasonSelect = document.getElementById('void_reason');
    if (voidReasonSelect) {
        voidReasonSelect.addEventListener('change', function() {
            const otherReasonContainer = document.getElementById('other-reason-container');
            if (this.value === 'Other') {
                otherReasonContainer.style.display = 'block';
                document.getElementById('other_reason').required = true;
            } else {
                otherReasonContainer.style.display = 'none';
                document.getElementById('other_reason').required = false;
            }
        });
    }

    // Load sale details for the modal
    function loadSaleDetails(saleId) {
        console.log('Loading sale details for:', saleId);
        
        fetch(`/app/sales/${saleId}/void/`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Sale details loaded:', data);
                
                if (data.error) {
                    showAlert('error', data.error);
                    return;
                }

                // Populate sale details
                document.getElementById('void-sale-id').textContent = `#${data.sale_id}`;
                document.getElementById('void-sale-date').textContent = data.date_time;
                document.getElementById('void-sale-customer').textContent = data.customer;
                document.getElementById('void-sale-amount').textContent = `₱${parseFloat(data.total_amount).toFixed(2)}`;
                document.getElementById('void-sale-payment').textContent = data.payment_method;
                document.getElementById('void-sale-id-input').value = data.sale_id;

                // Reset form
                voidSaleForm.reset();
                document.getElementById('other-reason-container').style.display = 'none';
                
                console.log('Sale details populated successfully');
            })
            .catch(error => {
                console.error('Error loading sale details:', error);
                showAlert('error', 'Error loading sale details. Please try again.');
            });
    }

    // Handle void confirmation
    confirmVoidBtn.addEventListener('click', function() {
        console.log('Confirm void clicked');
        const formData = new FormData(voidSaleForm);
        
        // Validate form
        if (!validateVoidForm(formData)) {
            return;
        }

        console.log('Form validated, showing loading modal');
        // Show loading modal
        loadingModal.show();

        // Submit void request
        fetch(`/app/sales/${currentSaleId}/void/`, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Void response:', data);
            loadingModal.hide();
            
            if (data.success) {
                showAlert('success', data.message);
                bootstrap.Modal.getInstance(voidSaleModal).hide();
                
                // Reload the page after a short delay to show updated status
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            } else {
                showAlert('error', data.error || 'Error voiding sale.');
            }
        })
        .catch(error => {
            loadingModal.hide();
            console.error('Fetch error:', error);
            showAlert('error', 'Network error. Please try again.');
        });
    });

    // Validate void form
    function validateVoidForm(formData) {
        const username = formData.get('admin_username');
        const password = formData.get('admin_password');
        const reason = formData.get('void_reason');
        const otherReason = formData.get('other_reason');

        if (!username || !password) {
            showAlert('error', 'Please enter admin credentials.');
            return false;
        }

        if (!reason) {
            showAlert('error', 'Please select a reason for voiding.');
            return false;
        }

        if (reason === 'Other' && (!otherReason || otherReason.trim() === '')) {
            showAlert('error', 'Please specify the reason for voiding.');
            return false;
        }

        return true;
    }

    // Utility function to get CSRF token
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Show alert message
    function showAlert(type, message) {
        console.log('Showing alert:', type, message);
        
        // Remove existing alerts
        const existingAlerts = document.querySelectorAll('.alert-dismissible');
        existingAlerts.forEach(alert => alert.remove());

        // Create new alert
        const alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
        const alertHtml = `
            <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;

        // Insert at the top of the content
        const content = document.querySelector('.container-fluid');
        if (content) {
            content.insertAdjacentHTML('afterbegin', alertHtml);
        }

        // Auto-remove after 5 seconds
        setTimeout(() => {
            const alert = document.querySelector('.alert-dismissible');
            if (alert) {
                alert.remove();
            }
        }, 5000);
    }

    // Reset form when modal is hidden
    voidSaleModal.addEventListener('hidden.bs.modal', function() {
        console.log('Modal hidden, resetting form');
        voidSaleForm.reset();
        document.getElementById('other-reason-container').style.display = 'none';
        currentSaleId = null;
    });

    // Void Sale functionality - Simple working version
console.log('Void sale JS loaded');
});