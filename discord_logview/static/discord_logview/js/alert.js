window.addEventListener('DOMContentLoaded', (event) => {
    document.querySelectorAll('.alert').forEach((alert) => {
        setTimeout(function () {
            alert.classList.add('disappearing');
            setTimeout(function () {
                alert.remove();
            }, 1000);
        }, 5000);
    });
});