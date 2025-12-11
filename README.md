# OCR API Service

This repository contains a production-grade Optical Character Recognition (OCR) microservice designed to extract text from images with high reliability. The service is built using **FastAPI** and **Tesseract OCR**, fully containerized with **Docker**, and deployed using a serverless architecture on **AWS App Runner**.

---

## Deployment Status & Documentation

The application is currently live and accessible publicly.

* **Service Endpoint:** [https://zj4m2pkzip.us-east-1.awsapprunner.com](https://zj4m2pkzip.us-east-1.awsapprunner.com)
* **API Specification (Swagger UI):** [https://zj4m2pkzip.us-east-1.awsapprunner.com/docs](https://zj4m2pkzip.us-east-1.awsapprunner.com/docs)

---

## Architecture & Infrastructure Strategy

### Infrastructure Agnosticism (GCP vs. AWS)
The initial requirements for this project suggested Google Cloud Run. However, this solution was deliberately deployed to **AWS App Runner** to demonstrate a cloud-agnostic container strategy.

By encapsulating the application logic, dependencies, and the OCR engine entirely within a Docker image, this solution achieves complete portability. The architecture decouples the workload from the specific cloud provider. Consequently, this exact container image should be compatible with Google Cloud Run, AWS ECS, Azure Container Apps without requiring any code modifications.

### Technical Stack
* **Runtime:** Python 3.9 (Slim).
* **Web Framework:** FastAPI.
* **OCR Engine:** Tesseract 4.0 (containerized).
* **Infrastructure:** AWS ECR (Elastic Container Registry) for artifact storage and AWS App Runner for serverless compute.

### Optimization Strategies
To ensure production readiness within a serverless environment, the following optimizations were implemented:
* **Concurrency Control:** Utilized `slowapi` to implement rate limiting, protecting the compute resources from abuse.
* **Latency Reduction:** Implemented in-memory caching using SHA-256 content hashing. Identical image uploads (regardless of filename) are detected immediately, returning cached results with near-zero latency.
* **Resource Management:** Configured OpenMP thread limits to prevent context-switching overhead in single-vCPU container environments.

---

## Functional Capabilities

In addition to standard text extraction, the API implements several advanced features:

* **Multi-Format Ingestion:** Native support for JPG, PNG, GIF, BIMP formats.
* **Image Preprocessing:** Basic thresholding is applied to improve accuracy on noisy images.
* **Batch Processing:** A dedicated endpoint allows for the sequential processing of multiple images in a single HTTP request.
* **Confidence Scoring:** The API aggregates word-level confidence data from Tesseract to provide an average confidence score (0.0 - 1.0) for the extracted text.
* **Metadata Extraction:** Returns technical metadata (dimensions and format) alongside the text payload.

---

## API Reference

### 1. Single Image Extraction

**Endpoint:** `POST /extract-text`
**Content-Type:** `multipart/form-data`

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `image` | File | Maximum size: 10MB. Supported formats: JPEG, PNG, GIF. |

**Example Request:**

```bash
curl -X POST -F "image=@document.jpg" \
[https://zj4m2pkzip.us-east-1.awsapprunner.com/extract-text](https://zj4m2pkzip.us-east-1.awsapprunner.com/extract-text)
````

**Example Response:**

```json
{
  "success": true,
  "text": "Extracted text content...",
  "confidence": 0.95,
  "metadata": {
    "width": 1024,
    "height": 768,
    "format": "JPEG"
  },
  "cached": false,
  "processing_time_ms": 342
}
```

### 2\. Batch Extraction

**Endpoint:** `POST /batch-extract`

**Example Request:**

```bash
curl -X POST \
  -F "images=@page1.png" \
  -F "images=@page2.jpg" \
  [https://zj4m2pkzip.us-east-1.awsapprunner.com/batch-extract](https://zj4m2pkzip.us-east-1.awsapprunner.com/batch-extract)
```

### Error Handling Standards

The API enforces strict HTTP status codes for error reporting:

  * **400 Bad Request:** Returned when the uploaded file is not a valid image or the format is unsupported.
  * **413 Payload Too Large:** Returned if the file size exceeds the 10MB limit.
  * **429 Too Many Requests:** Returned when the rate limit (10 requests/minute) is exceeded.

-----

## Setup & Deployment Guide

### 1\. Testing with Provided Samples

This repository includes a dataset of 37 test images located in the `test_images/` directory (filenames `1_test`, `2_test`, etc.). These samples cover various edge cases including handwriting, CAPTCHAs, and low-contrast text.

To test a specific sample (e.g., `1_test.jpg`) against the live API:

```bash
curl -X POST -F "image=@test_images/1_test.jpg" \
[https://zj4m2pkzip.us-east-1.awsapprunner.com/extract-text](https://zj4m2pkzip.us-east-1.awsapprunner.com/extract-text)
```

*(Note: Ensure you include the correct file extension present in the folder, such as .jpg, .png, or .bmp)*

### 2\. Local Development (Docker)

To replicate the cloud environment locally, use the following Docker commands:

```bash
# Build the Docker image
docker build -t fasapi-tesseract-ocr .

# Run the container (mapping port 8080)
docker run -p 8080:8080 fasapi-tesseract-ocr
```

### 3\. Cloud Deployment (AWS Pipeline)

Deployment is managed via the AWS Command Line Interface (CLI).

**Step A: Registry Configuration**

```bash
# Create the repository (if it does not exist)
aws ecr create-repository --repository-name fasapi-tesseract-ocr --region [REGION]

# Authenticate the Docker client with AWS ECR
aws ecr get-login-password --region [REGION] | docker login --username AWS --password-stdin [ACCOUNT_ID].dkr.ecr.[REGION].amazonaws.com
```

**Step B: Build and Push**

*Note: When building on Apple Silicon (M1/M2/M3), the `--platform` flag is mandatory to ensure the image runs on standard Linux cloud servers.*

```bash
# Build specifically for Linux x86_64 architecture
docker build --platform linux/amd64 -t fasapi-tesseract-ocr .

# Tag the image for the remote registry
docker tag fasapi-tesseract-ocr:latest [ACCOUNT_ID].dkr.ecr.[REGION][.amazonaws.com/fasapi-tesseract-ocr:latest](https://.amazonaws.com/fasapi-tesseract-ocr:latest)

# Push the image to AWS ECR
docker push [ACCOUNT_ID].dkr.ecr.[REGION][.amazonaws.com/fasapi-tesseract-ocr:latest](https://.amazonaws.com/fasapi-tesseract-ocr:latest)
```

**Step C: App Runner Service Configuration**

1.  Navigate to the **AWS App Runner** console.
2.  Create a new service and select **Container Image** as the source.
3.  Browse ECR and select the `fasapi-tesseract-ocr` image uploaded in the previous step.
4.  **Instance Configuration:**
      * vCPU: 1
      * Memory: 2 GB
5.  **Environment Variables:**
      * Key: `OMP_THREAD_LIMIT`
      * Value: `1`
      * *Rationale:* This prevents Tesseract from attempting to spawn multiple threads, which degrades performance in single-vCPU container environments.

-----

## Project Structure

```text
/
├── app.py             # Application entry point, API logic, and OCR pipeline
├── Dockerfile         # Container definition including Tesseract system dependencies
├── requirements.txt   # Python package dependencies
├── test_images/       # Directory containing 37 sample images for testing
└── README.md          # Technical documentation
```