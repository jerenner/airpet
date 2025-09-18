#ifndef AirPetTrajectory_h
#define AirPetTrajectory_h 1

#include "G4VTrajectory.hh"
#include "G4Allocator.hh"
#include "G4ThreeVector.hh"
#include "G4ParticleDefinition.hh"
#include "G4TrajectoryPoint.hh" // Needed for the container typedef

class G4Track;
class G4Step;

// Define the container type for trajectory points
typedef std::vector<G4VTrajectoryPoint*> TrajectoryPointContainer;


/// Custom trajectory class for Virtual PET.
///
/// It extends the default G4VTrajectory to store additional useful information
/// for analysis and visualization, such as initial/final volumes and creator process.

class AirPetTrajectory : public G4VTrajectory
{
public:
  // --- Constructors and Destructor ---
  AirPetTrajectory();
  AirPetTrajectory(const G4Track* aTrack);
  AirPetTrajectory(const AirPetTrajectory&); // Copy constructor
  virtual ~AirPetTrajectory();

  // --- Operators ---
  inline void* operator new(size_t);
  inline void  operator delete(void*);
  int operator==(const AirPetTrajectory& right) const { return (this == &right); }

  // --- G4VTrajectory virtual methods (Corrected) ---
  virtual void ShowTrajectory(std::ostream& os) const override;
  virtual void DrawTrajectory() const override;

  virtual void AppendStep(const G4Step* aStep) override;
  virtual G4int GetPointEntries() const override;
  virtual G4VTrajectoryPoint* GetPoint(G4int i) const override;
  virtual void MergeTrajectory(G4VTrajectory* secondTrajectory) override;

  // --- Getters (Marked with 'override' for correctness) ---
  G4String GetParticleName() const override { return fParticleDef->GetParticleName(); }
  G4int GetPDGEncoding() const override      { return fParticleDef->GetPDGEncoding(); }
  G4int GetTrackID() const override          { return fTrackID; }
  G4int GetParentID() const override         { return fParentID; }
  G4ThreeVector GetInitialMomentum() const override { return fMomentumInit; }
  G4double GetCharge() const override       { return fParticleDef->GetPDGCharge(); }

  // --- Custom Getters for our new data members ---
  G4String GetCreatorProcess() const    { return fCreatorProcess; }
  G4double GetMass() const              { return fParticleDef->GetPDGMass(); }
  G4double GetInitialTime() const       { return fTimeInit; }
  G4double GetFinalTime() const         { return fTimeFinal; }
  G4ThreeVector GetFinalMomentum() const   { return fMomentumFinal; }
  G4ThreeVector GetInitialPosition() const { return fPositionInit; }
  G4ThreeVector GetFinalPosition() const   { return fPositionFinal; }
  G4String GetInitialVolume() const     { return fVolInit; }
  G4String GetFinalVolume() const       { return fVolFinal; }
  G4ThreeVector GetParentMomentum() const  { return fParentMomentum; }

  // --- Setters ---
  void SetFinalTime(G4double t)              { fTimeFinal = t; }
  void SetFinalMomentum(const G4ThreeVector& p) { fMomentumFinal = p; }
  void SetFinalPosition(const G4ThreeVector& pos) { fPositionFinal = pos; }
  void SetFinalVolume(const G4String& vol)   { fVolFinal = vol; }
  void SetParentMomentum(const G4ThreeVector& p) { fParentMomentum = p; }

private:
  TrajectoryPointContainer* fPositionRecord;

  G4ParticleDefinition* fParticleDef;
  G4int                 fTrackID;
  G4int                 fParentID;
  G4double              fTimeInit;
  G4double              fTimeFinal;
  G4ThreeVector         fParentMomentum;
  G4ThreeVector         fMomentumInit;
  G4ThreeVector         fMomentumFinal;
  G4ThreeVector         fPositionInit;
  G4ThreeVector         fPositionFinal;
  G4String              fVolInit;
  G4String              fVolFinal;
  G4String              fCreatorProcess;

  static G4ThreadLocal G4Allocator<AirPetTrajectory>* fAllocator;
};


inline void* AirPetTrajectory::operator new(size_t)
{
  if (!fAllocator) {
    fAllocator = new G4Allocator<AirPetTrajectory>;
  }
  return (void*)fAllocator->MallocSingle();
}

inline void AirPetTrajectory::operator delete(void* aTrajectory)
{
  fAllocator->FreeSingle((AirPetTrajectory*)aTrajectory);
}

#endif