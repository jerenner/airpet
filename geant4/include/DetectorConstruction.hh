#ifndef DetectorConstruction_h
#define DetectorConstruction_h 1

#include "G4VUserDetectorConstruction.hh"
#include "G4GDMLParser.hh"
#include "G4ThreeVector.hh"
#include "globals.hh"
#include <map>
#include <vector>

// Forward declarations to avoid including heavy headers
class G4VPhysicalVolume;
class G4GenericMessenger;
class G4UImessenger;
/// The DetectorConstruction class.
///
/// This class is responsible for constructing the detector geometry.
/// In this application, it does not define geometry programmatically. Instead,
/// it loads a geometry from a GDML file specified via a UI command.
/// It also manages the assignment of sensitive detectors to logical volumes,
/// also controlled by UI commands.

class DetectorConstruction : public G4VUserDetectorConstruction
{
public:
  DetectorConstruction();
  virtual ~DetectorConstruction();

  // G4VUserDetectorConstruction mandatory methods
  virtual G4VPhysicalVolume* Construct() override;
  virtual void ConstructSDandField() override;

  // Messenger-callable methods
  void SetGDMLFile(G4String filename);
  void SetSensitiveDetector(G4String logicalVolumeName, G4String sdName);
  void SetGlobalMagneticField(G4ThreeVector value);
  void SetGlobalElectricField(G4ThreeVector value);
  void SetLocalMagneticField(G4String assignmentPayload);
  void SetLocalElectricField(G4String assignmentPayload);
  void SetRegionCutsAndLimits(G4String assignmentPayload);

private:
  struct RegionControlConfig
  {
    std::vector<G4String> targetVolumeNames;
    G4double productionCutMm = 0.;
    G4double maxStepMm = 0.;
    G4double maxTrackLengthMm = 0.;
    G4double maxTimeNs = 0.;
    G4double minKineticEnergyMeV = 0.;
    G4double minRangeMm = 0.;
  };

  void DefineCommands();

  // Member variables
  G4GDMLParser fParser;
  G4VPhysicalVolume* fWorldVolume;
  G4GenericMessenger* fMessenger;
  G4UImessenger* fGlobalFieldMessenger;
  G4ThreeVector fGlobalMagneticField;
  G4ThreeVector fGlobalElectricField;
  std::map<G4String, G4ThreeVector> fLocalMagFieldAssignments;
  std::map<G4String, G4ThreeVector> fLocalElecFieldAssignments;
  std::map<G4String, RegionControlConfig> fRegionControlAssignments;

  G4String fGDMLFilename;
  std::map<G4String, G4String> fSensitiveDetectorsMap;
};

#endif
