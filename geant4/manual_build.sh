#!/bin/bash
G4FLAGS=$(/Users/marth/miniconda/envs/airpet/bin/geant4-config --cflags)
G4LIBS=$(/Users/marth/miniconda/envs/airpet/bin/geant4-config --libs)
LIB_DIR="/Users/marth/miniconda/envs/airpet/lib"
SRC_DIR="/Users/marth/projects/airpet/geant4"
INCLUDE_DIR="$SRC_DIR/include"

mkdir -p $SRC_DIR/build
cd $SRC_DIR/build

g++ -O3 -std=c++17 $G4FLAGS -DG4ANALYSIS_USE_HDF5 -I$INCLUDE_DIR \
    $SRC_DIR/main.cc $SRC_DIR/src/*.cc \
    -o airpet-sim \
    -Wl,-rpath,$LIB_DIR \
    $G4LIBS -lxerces-c -lexpat -lz -lhdf5
