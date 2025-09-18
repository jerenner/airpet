#ifndef EventAction_h
#define EventAction_h 1

#include "G4UserEventAction.hh"
#include "G4GenericMessenger.hh"
#include "globals.hh"
#include <vector>

// Forward declarations
class G4Event;

/// The EventAction class.
///
/// This class handles actions at the beginning and end of each event.
/// Its main role is to retrieve data from sensitive detector hits collections
/// and from the trajectory container, and then fill the n-tuples defined in RunAction.

class EventAction : public G4UserEventAction
{
public:
  EventAction();
  virtual ~EventAction();

  // --- G4UserEventAction virtual methods ---
  virtual void BeginOfEventAction(const G4Event* event) override;
  virtual void EndOfEventAction(const G4Event* event) override;

  // Method to be called by a messenger command
  void SetPrintTracksToFile(G4bool value) { fPrintTracksToFile = value; }

private:
    void WriteTracksToFile(const G4Event* event);

  // A vector to store the integer IDs of all hits collections.
  // This is populated once in the first event.
  std::vector<G4int> fHitsCollectionIDs;

  // Flag to enable trajectory output to file.
  G4bool fPrintTracksToFile;
  G4GenericMessenger* fMessenger;
};

#endif