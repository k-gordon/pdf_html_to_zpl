let aspectRatio = 1;
let ratioLocked = true;
let originalWidth = 0;
let originalHeight = 0;

document.getElementById('file').addEventListener('change', async function(event) {
    const file = event.target.files[0];
    const fileURL = URL.createObjectURL(file);

    // Show original PDF immediately
    document.getElementById('pdf-preview').src = fileURL;

    // Get metadata and create scaled version
    const formData = new FormData();
    formData.append('file', file);
    formData.append('scaling', document.getElementById('scaling').value);
    formData.append('width', document.getElementById('width').value);
    formData.append('height', document.getElementById('height').value);
    formData.append('dpi', document.getElementById('dpi').value || "203");

    try {
        // Get metadata first
        const metadataResponse = await fetch('/extract_pdf_metadata', {
            method: 'POST',
            body: formData
        });
        const metadata = await metadataResponse.json();
        originalWidth = metadata.width;
        originalHeight = metadata.height;
        aspectRatio = originalWidth / originalHeight;
        
        // Apply scaling mode and update form
        applyScalingMode();
        document.getElementById('width').value = metadata.width.toFixed(2);
        document.getElementById('height').value = metadata.height.toFixed(2);
        if (!document.getElementById('dpi').value) {
            document.getElementById('dpi').value = "203";
        }

        // Get scaled preview
        const scaleResponse = await fetch('/scale_pdf', {
            method: 'POST',
            body: formData
        });

        if (scaleResponse.ok) {
            const result = await scaleResponse.json();
            // Show scaled preview instead of original
            document.getElementById('pdf-preview').src = result.scaled_url;
        }

    } catch (error) {
        console.error('Error:', error);
        // Original preview remains if scaling fails
    }
});

document.getElementById('upload-form').addEventListener('submit', async function(event) {
    event.preventDefault();
    const formData = new FormData();
    
    // Get the file
    const fileInput = document.getElementById('file');
    if (!fileInput.files || fileInput.files.length === 0) {
        alert('Please select a PDF file first');
        return;
    }
    formData.append('file', fileInput.files[0]);

    // Add other form fields with proper parsing for checkboxes
    formData.append('width', document.getElementById('width').value);
    formData.append('height', document.getElementById('height').value);
    formData.append('dpi', document.getElementById('dpi').value);
    formData.append('format', document.getElementById('format').value);
    formData.append('invert', document.getElementById('invert').checked);
    formData.append('dither', document.getElementById('dither').checked);
    formData.append('threshold', document.getElementById('threshold').value);
    formData.append('split_pages', document.getElementById('split_pages').checked);
    formData.append('scaling', document.getElementById('scaling').value);

    try {
        const response = await fetch('/upload_pdf', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        const zplContent = result.zpl_content.replace(/\\n/g, '\n');
        document.getElementById('output').textContent = zplContent;
        
        // Update the PDF preview with the scaled version
        const pdfPreview = document.getElementById('pdf-preview');
        pdfPreview.src = result.preview_url;

        // Update the ZPL preview
        const zplRender = document.getElementById('zpl-render');
        zplRender.classList.remove('hidden');
        zplRender.innerHTML = `<embed src="${result.zpl_preview_url}" type="application/pdf" style="width:100%; height:600px;">`;

    } catch (error) {
        console.error('Error:', error);
        alert('Failed to convert PDF. Please check the console for details.');
    }
});

const dropArea = document.getElementById('drop-area');

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

dropArea.addEventListener('drop', handleDrop, false);

async function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    document.getElementById('file').files = files;
    const file = files[0];
    const fileURL = URL.createObjectURL(file);
    document.getElementById('pdf-preview').src = fileURL;

    // Use pdfplumber to extract PDF metadata on the server side
    const formData = new FormData();
    formData.append('file', file);
    const response = await fetch('/extract_pdf_metadata', {
        method: 'POST',
        body: formData
    });
    const metadata = await response.json();
    originalWidth = metadata.width;
    originalHeight = metadata.height;
    aspectRatio = originalWidth / originalHeight;
    document.getElementById('width').value = metadata.width.toFixed(2);
    document.getElementById('height').value = metadata.height.toFixed(2);
    document.getElementById('dpi').value = metadata.dpi;
}

// Add click handler for the drop area
document.getElementById('drop-area').addEventListener('click', function() {
    document.getElementById('file').click();
});

document.getElementById('copy-button').addEventListener('click', function() {
    const output = document.getElementById('output').textContent;
    navigator.clipboard.writeText(output).then(() => {
        showToast('ZPL content copied to clipboard');
    }).catch(err => {
        console.error('Failed to copy text: ', err);
    });
});

function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.remove('hidden');
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3000);
}

// Add width validation
document.getElementById('width').addEventListener('input', function(e) {
    const width = parseFloat(e.target.value);
    if (width > 15) {
        e.target.setCustomValidity('Width cannot exceed 15 inches for preview');
    } else {
        e.target.setCustomValidity('');
    }
    if (ratioLocked && aspectRatio) {
        document.getElementById('height').value = (width / aspectRatio).toFixed(2);
    }
});

document.getElementById('height').addEventListener('input', function(e) {
    if (ratioLocked && aspectRatio) {
        const height = parseFloat(e.target.value);
        document.getElementById('width').value = (height * aspectRatio).toFixed(2);
    }
});

document.getElementById('ratio-lock').addEventListener('click', function() {
    ratioLocked = !ratioLocked;
    const icon = document.getElementById('ratio-lock-icon');
    if (ratioLocked) {
        icon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>`;
    } else {
        icon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 11V7a4 4 0 118 0m-4 8v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2z"/>`;
    }
});

function applyScalingMode() {
    const mode = document.getElementById('scaling').value;
    const width = document.getElementById('width');
    const height = document.getElementById('height');
    
    if (mode === 'fit') {
        // Calculate dimensions maintaining aspect ratio
        if (originalWidth > originalHeight * aspectRatio) {
            width.value = originalWidth.toFixed(2);
            height.value = (originalWidth / aspectRatio).toFixed(2);
        } else {
            height.value = originalHeight.toFixed(2);
            width.value = (originalHeight * aspectRatio).toFixed(2);
        }
    } else { // stretch
        width.value = originalWidth.toFixed(2);
        height.value = originalHeight.toFixed(2);
    }
}

document.getElementById('scaling').addEventListener('change', applyScalingMode);

// Add tab switching functionality
function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-button').forEach(button => {
        const isActive = button.getAttribute('data-tab') === tabName;
        button.classList.toggle('border-blue-500', isActive);
        button.classList.toggle('text-blue-600', isActive);
        button.classList.toggle('border-transparent', !isActive);
        button.classList.toggle('text-gray-500', !isActive);
    });

    // Show/hide content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
    });
    document.getElementById(`${tabName}-tab`).classList.remove('hidden');
}
