// Frontend Integration Guide for Architecture Deployment
// Add these endpoints to your UI application

const AGUI_API_BASE = 'http://localhost:9595/api';

/**
 * Parse a Mermaid diagram and extract AWS resources
 */
async function parseArchitectureMermaid(mermaidContent, provider = 'claude') {
  try {
    const response = await fetch(`${AGUI_API_BASE}/architecture/parse-mermaid`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mermaid: mermaidContent })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error parsing Mermaid:', error);
    throw error;
  }
}

/**
 * Upload and parse an architecture image using vision API
 */
async function parseArchitectureImage(file, provider = 'claude') {
  try {
    // Validate file type
    const allowedTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
      throw new Error(`Invalid file type: ${file.type}. Allowed: PNG, JPG, GIF, WebP`);
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    const url = new URL(`${AGUI_API_BASE}/architecture/parse-image`);
    url.searchParams.append('provider', provider);
    
    const response = await fetch(url, {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error parsing architecture image:', error);
    throw error;
  }
}

/**
 * Generate Terraform code from parsed architecture
 */
async function generateTerraform(architecture, provider = 'claude') {
  try {
    const response = await fetch(`${AGUI_API_BASE}/architecture/generate-terraform`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ architecture })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error generating Terraform:', error);
    throw error;
  }
}

/**
 * Deploy architecture (generate + plan in one call)
 */
async function deployArchitecture(architecture, provider = 'claude') {
  try {
    const response = await fetch(`${AGUI_API_BASE}/architecture/deploy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ architecture })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error deploying architecture:', error);
    throw error;
  }
}

/**
 * Full workflow: Mermaid text → Terraform → Deploy
 */
async function deployFromMermaid(mermaidContent, provider = 'claude') {
  try {
    console.log('Step 1: Parsing Mermaid diagram...');
    const architecture = await parseArchitectureMermaid(mermaidContent, provider);
    
    if (!architecture.success && architecture.type !== 'mermaid') {
      throw new Error('Failed to parse Mermaid diagram');
    }
    
    console.log('Step 2: Deploying architecture...');
    const deployResult = await deployArchitecture(architecture, provider);
    
    if (!deployResult.success) {
      throw new Error(`Deployment failed: ${deployResult.error}`);
    }
    
    console.log('Step 3: Architecture deployed!');
    return deployResult;
  } catch (error) {
    console.error('Error in deployment workflow:', error);
    throw error;
  }
}

/**
 * Full workflow: Image → Terraform → Deploy
 */
async function deployFromImage(imageFile, provider = 'claude') {
  try {
    console.log('Step 1: Analyzing architecture image...');
    const architecture = await parseArchitectureImage(imageFile, provider);
    
    if (!architecture.success) {
      throw new Error(`Failed to analyze image: ${architecture.error}`);
    }
    
    console.log('Step 2: Deploying architecture...');
    const deployResult = await deployArchitecture(architecture, provider);
    
    if (!deployResult.success) {
      throw new Error(`Deployment failed: ${deployResult.error}`);
    }
    
    console.log('Step 3: Architecture deployed!');
    return deployResult;
  } catch (error) {
    console.error('Error in image deployment workflow:', error);
    throw error;
  }
}

// ============================================================================
// UI Component Examples (React/Vue/Vanilla JS)
// ============================================================================

/**
 * Example: Mermaid Diagram Input Component (HTML/CSS/JS)
 */
class MermaidArchitectureInput {
  constructor(elementId) {
    this.element = document.getElementById(elementId);
    this.setupUI();
  }
  
  setupUI() {
    this.element.innerHTML = `
      <div class="architecture-input">
        <h3>AWS Architecture (Mermaid)</h3>
        <textarea id="mermaid-input" placeholder="graph LR&#10;  VPC[&quot;VPC&quot;]&#10;  EC2[&quot;EC2&quot;]&#10;  VPC --> EC2" rows="10"></textarea>
        <div class="buttons">
          <button id="parse-btn">Parse Architecture</button>
          <button id="deploy-btn">Deploy</button>
        </div>
        <div id="result" style="display:none;"></div>
      </div>
    `;
    
    this.setupEventListeners();
  }
  
  setupEventListeners() {
    document.getElementById('parse-btn').addEventListener('click', () => this.parseArchitecture());
    document.getElementById('deploy-btn').addEventListener('click', () => this.deployArchitecture());
  }
  
  async parseArchitecture() {
    const mermaidContent = document.getElementById('mermaid-input').value;
    if (!mermaidContent.trim()) {
      alert('Please enter Mermaid diagram content');
      return;
    }
    
    try {
      const result = await parseArchitectureMermaid(mermaidContent);
      this.showResult('Parsed Architecture', result);
    } catch (error) {
      this.showError(error.message);
    }
  }
  
  async deployArchitecture() {
    const mermaidContent = document.getElementById('mermaid-input').value;
    if (!mermaidContent.trim()) {
      alert('Please enter Mermaid diagram content');
      return;
    }
    
    try {
      const result = await deployFromMermaid(mermaidContent);
      this.showResult('Deployment Result', result);
    } catch (error) {
      this.showError(error.message);
    }
  }
  
  showResult(title, data) {
    const resultDiv = document.getElementById('result');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = `<h4>${title}</h4><pre>${JSON.stringify(data, null, 2)}</pre>`;
  }
  
  showError(message) {
    const resultDiv = document.getElementById('result');
    resultDiv.style.display = 'block';
    resultDiv.className = 'error';
    resultDiv.innerHTML = `<h4>Error</h4><p>${message}</p>`;
  }
}

/**
 * Example: Image Upload Component (HTML/CSS/JS)
 */
class ImageArchitectureInput {
  constructor(elementId) {
    this.element = document.getElementById(elementId);
    this.setupUI();
  }
  
  setupUI() {
    this.element.innerHTML = `
      <div class="image-input">
        <h3>AWS Architecture (Image)</h3>
        <input type="file" id="image-input" accept="image/png,image/jpeg,image/gif,image/webp" />
        <div class="buttons">
          <button id="parse-image-btn">Analyze Image</button>
          <button id="deploy-image-btn">Deploy</button>
        </div>
        <div id="image-result" style="display:none;"></div>
      </div>
    `;
    
    this.setupEventListeners();
  }
  
  setupEventListeners() {
    document.getElementById('parse-image-btn').addEventListener('click', () => this.analyzeImage());
    document.getElementById('deploy-image-btn').addEventListener('click', () => this.deployFromImage());
  }
  
  async analyzeImage() {
    const fileInput = document.getElementById('image-input');
    if (!fileInput.files.length) {
      alert('Please select an image file');
      return;
    }
    
    try {
      const result = await parseArchitectureImage(fileInput.files[0]);
      this.showResult('Image Analysis', result);
    } catch (error) {
      this.showError(error.message);
    }
  }
  
  async deployFromImage() {
    const fileInput = document.getElementById('image-input');
    if (!fileInput.files.length) {
      alert('Please select an image file');
      return;
    }
    
    try {
      const result = await deployFromImage(fileInput.files[0]);
      this.showResult('Deployment Result', result);
    } catch (error) {
      this.showError(error.message);
    }
  }
  
  showResult(title, data) {
    const resultDiv = document.getElementById('image-result');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = `<h4>${title}</h4><pre>${JSON.stringify(data, null, 2)}</pre>`;
  }
  
  showError(message) {
    const resultDiv = document.getElementById('image-result');
    resultDiv.style.display = 'block';
    resultDiv.className = 'error';
    resultDiv.innerHTML = `<h4>Error</h4><p>${message}</p>`;
  }
}

// ============================================================================
// CSS Styles (add to your stylesheet)
// ============================================================================

const styles = `
.architecture-input, .image-input {
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 20px;
  margin: 20px 0;
  background-color: #f9f9f9;
}

.architecture-input h3, .image-input h3 {
  margin-top: 0;
  color: #333;
}

.architecture-input textarea {
  width: 100%;
  font-family: monospace;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 10px;
  box-sizing: border-box;
}

.architecture-input input[type="file"],
.image-input input[type="file"] {
  margin: 10px 0;
}

.buttons {
  margin-top: 15px;
  display: flex;
  gap: 10px;
}

.buttons button {
  background-color: #007bff;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.buttons button:hover {
  background-color: #0056b3;
}

#result, #image-result {
  margin-top: 20px;
  background-color: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 15px;
  max-height: 400px;
  overflow: auto;
}

#result.error, #image-result.error {
  background-color: #f8d7da;
  border-color: #f5c6cb;
  color: #721c24;
}

#result pre, #image-result pre {
  background-color: #f4f4f4;
  padding: 10px;
  border-radius: 4px;
  overflow: auto;
  max-height: 300px;
}
`;

// ============================================================================
// Usage in HTML
// ============================================================================

/*
<html>
<head>
  <style>
    CSS styles go here (use the styles variable above)
  </style>
</head>
<body>
  <!-- Mermaid Input -->
  <div id="mermaid-architecture"></div>
  
  <!-- Image Input -->
  <div id="image-architecture"></div>
  
  <script src="architecture-deployment.js"></script>
  <script>
    // Initialize components
    const mermaidInput = new MermaidArchitectureInput('mermaid-architecture');
    const imageInput = new ImageArchitectureInput('image-architecture');
  </script>
</body>
</html>
*/

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    parseArchitectureMermaid,
    parseArchitectureImage,
    generateTerraform,
    deployArchitecture,
    deployFromMermaid,
    deployFromImage,
    MermaidArchitectureInput,
    ImageArchitectureInput
  };
}
