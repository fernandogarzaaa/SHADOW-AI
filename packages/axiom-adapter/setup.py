from setuptools import setup, find_packages

setup(
    name="axiom-adapter",
    version="0.1.0",
    description="AXIOM context packaging, redaction, and semantic routing adapter for SHADOW-AI.",
    author="Fernando Garza",
    license="MIT",
    packages=find_packages(include=["axiom_adapter", "axiom_adapter.*"], exclude=["tests", "tests.*"]),
    install_requires=[],
    python_requires=">=3.11",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
    ],
)
