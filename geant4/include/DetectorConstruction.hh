#ifndef DetectorConstruction_h
#define DetectorConstruction_h 1

#include "G4VUserDetectorConstruction.hh"
#include "G4GDMLParser.hh"
#include "globals.hh"
#include <map>

// Forward declarations to avoid including heavy headers
class G4VPhysicalVolume;
class G4GenericMessenger;

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

private:
  void DefineCommands();

  // Member variables
  G4GDMLParser fParser;
  G4VPhysicalVolume* fWorldVolume;
  G4GenericMessenger* fMessenger;

  G4String fGDMLFilename;
  std::map<G4String, G4String> fSensitiveDetectorsMap;
};

#endif