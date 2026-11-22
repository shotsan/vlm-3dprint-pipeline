from setuptools import setup, find_packages

setup(
    name="vlm-3dprint-pipeline",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pydantic>=2.0.0",
        "pillow>=10.0.0",
        "numpy>=1.24.0",
        "scipy>=1.10.0",
        "openai>=1.20.0",
        "anthropic>=0.20.0",
    ],
    entry_points={
        "console_scripts": [
            "vlm-print=vlm_pipeline.cli:main",
        ],
    },
)
