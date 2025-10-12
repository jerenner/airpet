#ifndef EventAction_h
#define EventAction_h 1

#include "G4UserEventAction.hh"
#include "G4UImessenger.hh"
#include "globals.hh"
#include <vector>

// Forward declarations
class G4Event;
class G4UIdirectory;
class G4UIcommand;

/// The EventAction class.
///
/// This class handles actions at the beginning and end of each event.
/// Its main role is to retrieve data from sensitive detector hits collections
/// and from the trajectory container, and then fill the n-tuples defined in RunAction.

class EventAction : public G4UserEventAction, public G4UImessenger
{
public:
  EventAction();
  virtual ~EventAction();

  // --- G4UserEventAction virtual methods ---
  virtual void BeginOfEventAction(const G4Event* event) override;
  virtual void EndOfEventAction(const G4Event* event) override;

  // --- G4UImessenger virtual method ---
  virtual void SetNewValue(G4UIcommand* command, G4String newValue) override;

  // Method to be called by a messenger command
  void SetTrackOutputDir(const G4String& dir) { fTrackOutputDir = dir; }
  void SetTrackEventRange(G4int start, G4int end);

private:
    void WriteTracksToFile(const G4Event* event);

  // A vector to store the integer IDs of all hits collections.
  // This is populated once in the first event.
  std::vector<G4int> fHitsCollectionIDs;

  // Flag to enable trajectory output to file.
  G4String fTrackOutputDir;
  
  // --- Messenger-related members ---
  G4UIdirectory*   fG4petDir;              
  G4UIdirectory*   fEventDir;              
  G4UIcommand*     fTrackOutputDirCmd;     
  G4UIcommand*     fSetTrackEventRangeCmd;

  // Event tracking range
  G4int fStartEventToTrack;
  G4int fEndEventToTrack;
};

#endif