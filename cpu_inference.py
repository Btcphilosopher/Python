"""
PyTorch CPU Inference Pipeline
------------------------------
A practical CPU-only inference implementation.

Features:
- CPU-only execution
- Model loading and evaluation
- Optional TorchScript compilation
- CPU thread optimisation
- Batch inference
- Inference benchmarking
- Basic error handling

Requirements:
    pip install torch
"""

import time
from pathlib import Path

import torch
import torch.nn as nn


# ============================================================
# 1. CPU CONFIGURATION
# ============================================================

DEVICE = torch.device("cpu")

# Configure CPU parallelism.
# Adjust these values to suit your processor.
CPU_THREADS = 4

torch.set_num_threads(CPU_THREADS)
torch.set_num_interop_threads(1)

print("PyTorch CPU Inference")
print(f"PyTorch version: {torch.__version__}")
print(f"Device: {DEVICE}")
print(f"CPU threads: {torch.get_num_threads()}")


# ============================================================
# 2. EXAMPLE NEURAL NETWORK
# ============================================================

class InferenceModel(nn.Module):
    """
    Example feed-forward neural network.

    Replace this architecture with your trained model.
    """

    def __init__(
        self,
        input_features: int = 128,
        hidden_features: int = 256,
        output_features: int = 10,
    ):
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(input_features, hidden_features),
            nn.ReLU(),
            nn.Linear(hidden_features, hidden_features),
            nn.ReLU(),
            nn.Linear(hidden_features, output_features),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x)


# ============================================================
# 3. MODEL LOADING
# ============================================================

def load_model(
    checkpoint_path: str | None = None,
) -> nn.Module:
    """
    Initialise a model and optionally load trained weights.

    The example model uses randomly initialised weights when
    no checkpoint is provided.
    """

    model = InferenceModel()

    if checkpoint_path is not None:
        path = Path(checkpoint_path)

        if not path.is_file():
            raise FileNotFoundError(
                f"Model checkpoint not found: {path}"
            )

        state_dict = torch.load(
            path,
            map_location=DEVICE,
            weights_only=True,
        )

        model.load_state_dict(state_dict)

    model = model.to(DEVICE)
    model.eval()

    return model


# ============================================================
# 4. CPU MODEL OPTIMISATION
# ============================================================

def optimise_model(model: nn.Module) -> nn.Module:
    """
    Apply CPU-friendly inference optimisations.

    Dynamic quantisation can reduce model size and accelerate
    supported linear layers on compatible CPU hardware.
    """

    model = model.eval()

    quantised_model = torch.ao.quantization.quantize_dynamic(
        model,
        {nn.Linear},
        dtype=torch.qint8,
    )

    return quantised_model


# ============================================================
# 5. INPUT PREPROCESSING
# ============================================================

def preprocess(
    inputs: torch.Tensor,
) -> torch.Tensor:
    """
    Prepare inputs for CPU inference.

    Expected shape:
        [batch_size, 128]

    Replace this function with application-specific
    preprocessing for images, text, audio, or other data.
    """

    if not isinstance(inputs, torch.Tensor):
        inputs = torch.tensor(inputs, dtype=torch.float32)

    inputs = inputs.to(
        device=DEVICE,
        dtype=torch.float32,
    )

    if inputs.ndim != 2:
        raise ValueError(
            "Expected a 2D tensor shaped [batch_size, features]."
        )

    if inputs.shape[1] != 128:
        raise ValueError(
            f"Expected 128 input features, got {inputs.shape[1]}."
        )

    return inputs.contiguous()


# ============================================================
# 6. INFERENCE EXECUTION
# ============================================================

@torch.inference_mode()
def run_inference(
    model: nn.Module,
    inputs: torch.Tensor,
) -> torch.Tensor:
    """
    Execute inference without gradient tracking.
    """

    inputs = preprocess(inputs)

    outputs = model(inputs)

    return outputs


# ============================================================
# 7. BENCHMARKING
# ============================================================

def benchmark(
    model: nn.Module,
    inputs: torch.Tensor,
    warmup_runs: int = 10,
    benchmark_runs: int = 100,
) -> dict[str, float]:
    """
    Measure CPU inference latency and throughput.
    """

    inputs = preprocess(inputs)

    # Warm up the execution path.
    for _ in range(warmup_runs):
        run_inference(model, inputs)

    start = time.perf_counter()

    for _ in range(benchmark_runs):
        run_inference(model, inputs)

    elapsed = time.perf_counter() - start

    total_samples = inputs.shape[0] * benchmark_runs

    average_latency_ms = (
        elapsed / benchmark_runs
    ) * 1000.0

    throughput = total_samples / elapsed

    return {
        "average_latency_ms": average_latency_ms,
        "throughput_samples_per_second": throughput,
        "benchmark_runs": float(benchmark_runs),
        "batch_size": float(inputs.shape[0]),
    }


# ============================================================
# 8. MAIN EXECUTION
# ============================================================

def main() -> None:
    """
    Initialise the model, run inference, and benchmark it.
    """

    # Set to a trained state_dict file when available.
    checkpoint_path = None

    model = load_model(checkpoint_path)

    # Optional CPU optimisation.
    optimised_model = optimise_model(model)

    # Generate example input.
    # Replace with real application data.
    batch_size = 32

    inputs = torch.randn(
        batch_size,
        128,
        dtype=torch.float32,
        device=DEVICE,
    )

    # Run standard inference.
    standard_outputs = run_inference(
        model,
        inputs,
    )

    # Run optimised inference.
    optimised_outputs = run_inference(
        optimised_model,
        inputs,
    )

    print("\nInference results")
    print("-----------------")
    print(f"Input shape: {tuple(inputs.shape)}")
    print(
        f"Standard output shape: "
        f"{tuple(standard_outputs.shape)}"
    )
    print(
        f"Optimised output shape: "
        f"{tuple(optimised_outputs.shape)}"
    )

    # Benchmark the standard model.
    standard_metrics = benchmark(
        model,
        inputs,
    )

    # Benchmark the optimised model.
    optimised_metrics = benchmark(
        optimised_model,
        inputs,
    )

    print("\nStandard CPU inference")
    print("----------------------")

    for key, value in standard_metrics.items():
        print(f"{key}: {value:.4f}")

    print("\nOptimised CPU inference")
    print("-----------------------")

    for key, value in optimised_metrics.items():
        print(f"{key}: {value:.4f}")

    print("\nInference complete.")


if __name__ == "__main__":
    main()
    
