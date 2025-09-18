#include "AirPetTrajectory.hh"
#include "G4Track.hh"
#include "G4VProcess.hh"
#include "G4VVisManager.hh"
#include "G4VisAttributes.hh"
#include "G4Polyline.hh"

G4ThreadLocal G4Allocator<AirPetTrajectory>* AirPetTrajectory::fAllocator = nullptr;

AirPetTrajectory::AirPetTrajectory()
  : G4VTrajectory(),
    fPositionRecord(nullptr),
    fParticleDef(nullptr),
    fTrackID(-1), fParentID(-1),
    fTimeInit(0.), fTimeFinal(0.)
{}

AirPetTrajectory::AirPetTrajectory(const G4Track* aTrack) : G4VTrajectory()
{
  fParticleDef    = aTrack->GetDefinition();
  fTrackID        = aTrack->GetTrackID();
  fParentID       = aTrack->GetParentID();
  fMomentumInit   = aTrack->GetMomentum();
  fPositionInit   = aTrack->GetVertexPosition();
  fVolInit        = aTrack->GetVolume()->GetName();
  fTimeInit       = aTrack->GetGlobalTime();
  fParentMomentum = G4ThreeVector(0,0,0);

  const G4VProcess* proc = aTrack->GetCreatorProcess();
  if (proc) {
    fCreatorProcess = proc->GetProcessName();
  } else {
    fCreatorProcess = "primary";
  }

  fPositionRecord = new TrajectoryPointContainer();
  fPositionRecord->push_back(new G4TrajectoryPoint(aTrack->GetPosition()));
}

AirPetTrajectory::AirPetTrajectory(const AirPetTrajectory& other)
  : G4VTrajectory(other) // Use base class copy constructor
{
  fParticleDef = other.fParticleDef;
  fTrackID = other.fTrackID;
  fParentID = other.fParentID;
  fTimeInit = other.fTimeInit;
  fTimeFinal = other.fTimeFinal;
  fParentMomentum = other.fParentMomentum;
  fMomentumInit = other.fMomentumInit;
  fMomentumFinal = other.fMomentumFinal;
  fPositionInit = other.fPositionInit;
  fPositionFinal = other.fPositionFinal;
  fVolInit = other.fVolInit;
  fVolFinal = other.fVolFinal;
  fCreatorProcess = other.fCreatorProcess;

  // Deep copy the position record
  fPositionRecord = new TrajectoryPointContainer();
  for (size_t i = 0; i < other.fPositionRecord->size(); ++i) {
      // We must cast the G4VTrajectoryPoint to the concrete G4TrajectoryPoint
      auto* oldPoint = dynamic_cast<G4TrajectoryPoint*>((*other.fPositionRecord)[i]);
      if (oldPoint) {
          fPositionRecord->push_back(new G4TrajectoryPoint(*oldPoint));
      }
  }
}

AirPetTrajectory::~AirPetTrajectory()
{
  if (fPositionRecord) {
    for (auto& i : *fPositionRecord) {
      delete i;
    }
    fPositionRecord->clear();
    delete fPositionRecord;
  }
}

void AirPetTrajectory::ShowTrajectory(std::ostream& os) const
{
  // Just use the base class implementation for now
  G4VTrajectory::ShowTrajectory(os);
}

void AirPetTrajectory::DrawTrajectory() const
{
  G4VVisManager* pVVisManager = G4VVisManager::GetConcreteInstance();
  if (!pVVisManager) return;

  G4Polyline polyline;
  for (size_t i = 0; i < fPositionRecord->size(); ++i) {
      polyline.push_back((*fPositionRecord)[i]->GetPosition());
  }

  G4Colour colour(0.2, 0.2, 0.2); // Default grey
  if (fParticleDef) {
    if (fParticleDef->GetPDGCharge() != 0.) {
      colour = G4Colour(0., 0., 1.); // Blue for charged
    } else {
      colour = G4Colour(0., 1., 0.); // Green for neutral
    }
  }

  G4VisAttributes attribs(colour);
  polyline.SetVisAttributes(attribs);
  pVVisManager->Draw(polyline);
}

void AirPetTrajectory::AppendStep(const G4Step* aStep)
{
  fPositionRecord->push_back(new G4TrajectoryPoint(aStep->GetPostStepPoint()->GetPosition()));
}

G4int AirPetTrajectory::GetPointEntries() const
{
  return fPositionRecord ? fPositionRecord->size() : 0;
}

G4VTrajectoryPoint* AirPetTrajectory::GetPoint(G4int i) const
{
  return (fPositionRecord && i < (G4int)fPositionRecord->size()) ? (*fPositionRecord)[i] : nullptr;
}


void AirPetTrajectory::MergeTrajectory(G4VTrajectory* secondTrajectory)
{
  if (!secondTrajectory) return;

  auto seco = dynamic_cast<AirPetTrajectory*>(secondTrajectory);
  if (!seco) return;

  G4int ent = seco->GetPointEntries();
  // Skip the first point of the second trajectory as it's a duplicate
  for (G4int i = 1; i < ent; ++i)
  {
    fPositionRecord->push_back((*(seco->fPositionRecord))[i]);
  }
  // The merged trajectory now owns the points, so we clear the second one
  // without deleting the points.
  (*(seco->fPositionRecord))[0] = nullptr; // Prevent double deletion
  seco->fPositionRecord->clear();
}