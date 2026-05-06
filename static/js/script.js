
/* Global helpers and UI interactions for dashboard and results */

function validateDriveURL(url) {
    const patterns = [
        /https:\/\/drive\.google\.com\/drive\/folders\/([a-zA-Z0-9_-]+)/,
        /https:\/\/drive\.google\.com\/open\?id=([a-zA-Z0-9_-]+)/,
        /https:\/\/drive\.google\.com\/folderview\?id=([a-zA-Z0-9_-]+)/
    ];
    
    for (const pattern of patterns) {
        if (pattern.test(url)) {
            return true;
        }
    }
    
    return false;
}

// Function to show loading spinner
function showLoadingSpinner() {
    const spinner = document.createElement('div');
    spinner.className = 'loading-spinner';
    spinner.innerHTML = '<div class="spinner"></div><p>Processing your images...</p>';
    document.body.appendChild(spinner);
}

// Function to hide loading spinner
function hideLoadingSpinner() {
    const spinner = document.querySelector('.loading-spinner');
    if (spinner) {
        spinner.remove();
    }
}

// Initialize dashboard form interactions
function initDashboardForm() {
    const driveInput = document.getElementById('drive_link');
    const driveError = document.getElementById('drive-error');
    const fileInput = document.getElementById('reference_image');
    const previewImg = document.getElementById('preview-img');
    const fileNameSpan = document.getElementById('file-name');
    const dropArea = document.getElementById('drop-area');
    const submitBtn = document.getElementById('submit-btn');
    const form = document.querySelector('form');

    // Drive URL validation
    driveInput.addEventListener('input', function() {
        if (!driveInput.value) {
            driveError.style.display = 'none';
            submitBtn.disabled = false;
            return;
        }
        if (!validateDriveURL(driveInput.value)) {
            driveError.textContent = 'Invalid Google Drive link format.';
            driveError.style.display = 'block';
            submitBtn.disabled = true;
        } else {
            driveError.style.display = 'none';
            submitBtn.disabled = false;
        }
    });

    // File selection and preview
    function handleFiles(files) {
        const file = files[0];
        if (!file) return;
        fileNameSpan.textContent = file.name;

        const reader = new FileReader();
        reader.onload = function(e) {
            previewImg.src = e.target.result;
            previewImg.style.display = 'block';
        };
        reader.readAsDataURL(file);
    }

    fileInput.addEventListener('change', function(e) {
        handleFiles(e.target.files);
    });

    // Drag-and-drop
    ['dragenter', 'dragover'].forEach(evt => {
        dropArea.addEventListener(evt, function(e) {
            e.preventDefault();
            e.stopPropagation();
            dropArea.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach(evt => {
        dropArea.addEventListener(evt, function(e) {
            e.preventDefault();
            e.stopPropagation();
            dropArea.classList.remove('drag-over');
        });
    });

    dropArea.addEventListener('drop', function(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length) {
            fileInput.files = files; // assign dropped files to input
            handleFiles(files);
        }
    });

    dropArea.addEventListener('click', function() {
        fileInput.click();
    });

    // Show spinner on submit (keep standard form submission)
    form.addEventListener('submit', function(e) {
        // final validation
        if (!driveInput.value || !fileInput.files.length) {
            e.preventDefault();
            if (!driveInput.value) {
                driveError.textContent = 'Please provide a Google Drive link.';
                driveError.style.display = 'block';
            }
            if (!fileInput.files.length) {
                alert('Please upload a reference photo.');
            }
            return;
        }

        showLoadingSpinner();
        submitBtn.disabled = true;
    });
}

// Initialize result page interactions (lightbox, copy)
function initResultPage() {
    const items = document.querySelectorAll('.image-item');
    const lightbox = document.getElementById('lightbox');
    const lbImg = document.getElementById('lightbox-img');
    const lbClose = document.querySelector('.lightbox-close');
    const lbDownload = document.getElementById('lightbox-download');
    const lbCopy = document.getElementById('lightbox-copy');

    function openLightbox(url) {
        lbImg.src = url;
        lbDownload.href = url;
        lightbox.style.display = 'flex';
    }

    function closeLightbox() {
        lightbox.style.display = 'none';
        lbImg.src = '';
    }

    items.forEach(item => {
        const url = item.getAttribute('data-image-url');
        item.addEventListener('click', function(e) {
            // allow copy/download buttons to handle themselves
            if (e.target.classList.contains('btn-copy') || e.target.classList.contains('btn-download')) return;
            openLightbox(url);
        });

        const copyBtn = item.querySelector('.btn-copy');
        if (copyBtn) {
            copyBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                const link = copyBtn.getAttribute('data-link');
                if (navigator.clipboard) {
                    navigator.clipboard.writeText(link).then(() => {
                        copyBtn.textContent = 'Copied!';
                        setTimeout(() => copyBtn.textContent = 'Copy Link', 1500);
                    });
                }
            });
        }
    });

    lbClose.addEventListener('click', closeLightbox);
    lightbox.addEventListener('click', function(e) {
        if (e.target === lightbox) closeLightbox();
    });

    lbCopy.addEventListener('click', function() {
        const link = lbDownload.href;
        if (navigator.clipboard) {
            navigator.clipboard.writeText(link).then(() => {
                lbCopy.textContent = 'Copied!';
                setTimeout(() => lbCopy.textContent = 'Copy Link', 1500);
            });
        }
    });
}

// Add CSS for loading spinner and new UI elements
const style = document.createElement('style');
style.textContent = `
    .loading-spinner { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(255,255,255,0.85); display:flex; flex-direction:column; justify-content:center; align-items:center; z-index:1000; }
    .spinner { border: 8px solid #f3f3f3; border-top: 8px solid #4285f4; border-radius:50%; width:60px; height:60px; animation: spin 2s linear infinite; margin-bottom:12px; }
    @keyframes spin { 0% { transform: rotate(0deg);} 100% { transform: rotate(360deg);} }

    .drop-area { border:2px dashed #c8d0db; padding:18px; border-radius:8px; text-align:center; cursor:pointer; transition: background .2s ease, border-color .2s ease; background:#fbfdff; }
    .drop-area.drag-over { background:#eef6ff; border-color:#6aa0ff; }
    .drop-message { color:#6b7280; }
    .preview-img { max-width:120px; max-height:120px; margin-top:12px; border-radius:6px; box-shadow:0 2px 8px rgba(0,0,0,0.08); }

    .image-overlay .btn-download { margin-left:8px; }
    .image-overlay .btn-copy { margin-left:8px; }

    .lightbox { position:fixed; inset:0; display:flex; align-items:center; justify-content:center; background:rgba(0,0,0,0.7); z-index:2000; }
    .lightbox-content { position:relative; background:white; padding:18px; border-radius:8px; max-width:90%; max-height:90%; box-shadow: 0 8px 32px rgba(0,0,0,0.6); text-align:center; }
    .lightbox img { max-width:100%; max-height:70vh; display:block; margin:0 auto 12px; }
    .lightbox-close { position:absolute; top:8px; right:8px; background:transparent; border:none; font-size:28px; cursor:pointer; }
    .lightbox-actions { display:flex; gap:10px; justify-content:center; }
`;
document.head.appendChild(style);