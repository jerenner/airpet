#include "AirPetSensitiveDetector.hh"
#include "G4HCofThisEvent.hh"
#include "G4SDManager.hh"
#include "G4Step.hh"
#include "G4Track.hh"
#include "G4TouchableHistory.hh"
#include "G4ios.hh"

AirPetSensitiveDetector::AirPetSensitiveDetector(const G4String& name)
 : G4VSensitiveDetector(name),
   fHitsCollection(nullptr)
{
  // The name of the hits collection is declared here.
  // This name will be used by the EventAction to retrieve the collection.
  collectionName.insert(name + "HitsCollection");
}

AirPetSensitiveDetector::~AirPetSensitiveDetector()
{}

void AirPetSensitiveDetector::Initialize(G4HCofThisEvent* hce)
{
  // Create a new hits collection for this event
  fHitsCollection = new AirPetHitsCollection(SensitiveDetectorName, collectionName[0]);

  // Get a unique ID for this collection from the SDManager
  G4int hcID = G4SDManager::GetSDMpointer()->GetCollectionID(collectionName[0]);

  // Add the collection to the Hits Collection of this Event
  hce->AddHitsCollection(hcID, fHitsCollection);
}

G4bool AirPetSensitiveDetector::ProcessHits(G4Step* aStep, G4TouchableHistory* /*ROhist*/)
{
  // Get the energy deposited in this step
  G4double edep = aStep->GetTotalEnergyDeposit();

  // If no energy was deposited, do nothing
  if (edep == 0.) return false;

  // Create a new hit
  AirPetHit* newHit = new AirPetHit();

  // Get the track that produced this hit
  G4Track* track = aStep->GetTrack();
  newHit->SetTrackID(track->GetTrackID());
  newHit->SetParentID(track->GetParentID());
  newHit->SetParticleName(track->GetDefinition()->GetParticleName());

  // Get information from the PreStepPoint (where the step started)
  G4StepPoint* preStepPoint = aStep->GetPreStepPoint();
  G4TouchableHistory* touchable = (G4TouchableHistory*)(preStepPoint->GetTouchable());
  newHit->SetVolumeName(touchable->GetVolume()->GetLogicalVolume()->GetName());
  newHit->SetCopyNo(touchable->GetVolume()->GetCopyNo());

  // Get information from the PostStepPoint (where the step ended)
  G4StepPoint* postStepPoint = aStep->GetPostStepPoint();
  newHit->SetEdep(edep);
  newHit->SetPosition(postStepPoint->GetPosition());
  newHit->SetTime(postStepPoint->GetGlobalTime());

  // Add the hit to our collection for this event
  fHitsCollection->insert(newHit);

  return true;
}

void AirPetSensitiveDetector::EndOfEvent(G4HCofThisEvent* /*hce*/)
{
  // This method is called at the very end of the event processing.
  // Can be used to print a summary of hits for this SD.
  // G4int nofHits = fHitsCollection->entries();
  // if (nofHits > 0) {
  //   G4cout << G4endl
  //          << "--------> Hits Collection " << SensitiveDetectorName << ": "
  //          << nofHits << " hits in " << GetName() << ":" << G4endl;
  //   for (G4int i = 0; i < nofHits; i++) (*fHitsCollection)[i]->Print();
  // }
}
