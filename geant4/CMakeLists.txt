# CMake build file for the AirPet Geant4 Simulation Application

# Minimum CMake version required
cmake_minimum_required(VERSION 3.16)

# Project Name
project(AirPetSim LANGUAGES C CXX)

# Find the Geant4 package and its components.
# This command will locate your Geant4 installation. For this to work,
# the user must have sourced the geant4.sh script from their Geant4 build
# before running cmake. (e.g., source /path/to/geant4-install/bin/geant4.sh)
find_package(Geant4 REQUIRED COMPONENTS ui_all vis_all)

# Add Geant4 include directories and compile definitions to our target.
# G4vis_USE_QT is needed for the GUI. G4UI_USE_QT for UI sessions.
include(${Geant4_USE_FILE})

# Locate sources and headers for this project
#
include_directories(${PROJECT_SOURCE_DIR}/include
                     ${Geant4_INCLUDE_DIR} )

# Define the C++ standard (Geant4 requires at least C++17)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- Locate all header and source files ---
# This automatically finds all .hh files in the include/ directory
file(GLOB_RECURSE HEADERS
    "${PROJECT_SOURCE_DIR}/include/*.hh"
)

# This automatically finds all .cc files in the src/ directory
file(GLOB_RECURSE SOURCES
    "${PROJECT_SOURCE_DIR}/src/*.cc"
)

# --- Define the executable ---
# This creates our target executable named "airpet-sim"
add_executable(airpet-sim main.cc ${SOURCES} ${HEADERS})

# Link the executable against the Geant4 libraries we found.
# Geant4::G4run handles core simulation components.
# Geant4::G4vis handles visualization drivers.
# Geant4::G4ui_all handles the terminal and GUI user interfaces.
target_link_libraries(airpet-sim ${Geant4_LIBRARIES})

# --- Installation ---
# This section defines what happens when a user runs "make install".
# It will install the executable and any necessary resource files.
install(TARGETS airpet-sim
        DESTINATION bin
)

# --- Final Output ---
message(STATUS "Geant4 libraries found: ${Geant4_LIBRARIES}")
message(STATUS "Build will produce executable: airpet-sim")