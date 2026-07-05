from setuptools import setup, find_packages

setup(
    name="memory-engine",
    version="0.1.0",
    description="Encrypted local memory storage and retrieval engine for SHADOW-AI.",
    author="Fernando Garza",
    license="MIT",
    packages=find_packages(include=["memory_engine", "memory_engine.*"], exclude=["tests", "tests.*"]),
    install_requires=["pydantic>=2.10.0,<3", "cryptography>=44.0.0,<45"],
    python_requires=">=3.11",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
    ],
)
