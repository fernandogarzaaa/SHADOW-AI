from setuptools import setup, find_packages

setup(
    name="memory-engine",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["pydantic>=2.10.0", "cryptography>=44.0.0"],
    python_requires=">=3.11",
)
