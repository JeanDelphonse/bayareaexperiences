/**
 * booking.js — Progressive enhancement for booking form.
 * The core timeslot fetch logic lives inline in book.html (uses Jinja2 vars).
 * This file handles additional UX enhancements.
 */
document.addEventListener('DOMContentLoaded', function () {
  // Auto-generate slug from name in admin experience form
  const nameInput = document.querySelector('input[name="name"]');
  const slugInput = document.querySelector('input[name="slug"]');

  if (nameInput && slugInput && !slugInput.value) {
    nameInput.addEventListener('input', function () {
      slugInput.value = this.value
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
    });
  }

  // Booking form: require timeslot before submit
  const bookingForm = document.getElementById('bookingForm');
  const submitBtn   = document.getElementById('submitBtn');
  if (bookingForm && submitBtn) {
    bookingForm.addEventListener('submit', function (e) {
      const timeslotId = document.getElementById('timeslot_id').value;
      if (!timeslotId) {
        e.preventDefault();
        alert('Please select a date and timeslot before continuing.');
      }
    });
  }
});
